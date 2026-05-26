import os
import re
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
from urllib.parse import urlparse, urljoin
import concurrent.futures

# Load environment variables
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# Helper function to crawl a single page and return cleaned text, headers, and soup
def fetch_and_clean_page(url, headers):
    try:
        response = requests.get(url, headers=headers, timeout=8, verify=True)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        # Fallback to HTTP if HTTPS failed
        if url.startswith('https://'):
            http_url = url.replace('https://', 'http://')
            try:
                response = requests.get(http_url, headers=headers, timeout=8, verify=True)
                response.raise_for_status()
            except requests.exceptions.RequestException:
                return None
        else:
            return None

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Get title and meta
    title = soup.title.string.strip() if soup.title else ""
    meta_desc_tag = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
    meta_desc = meta_desc_tag['content'].strip() if meta_desc_tag and meta_desc_tag.has_attr('content') else ""

    # Clean layout and code tags
    for element in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript", "svg", "path", "symbol", "canvas", "form"]):
        element.decompose()

    # Extract headings
    headings = []
    for tag in ['h1', 'h2', 'h3', 'h4']:
        for h in soup.find_all(tag):
            text = h.get_text().strip()
            if text and len(text) > 3:
                headings.append(f"{tag.upper()}: {text}")

    # Extract clean text segments
    text_blocks = []
    for p in soup.find_all(['p', 'li', 'article', 'section', 'td', 'div']):
        if p.name == 'div' and p.find(['p', 'li', 'article', 'section']):
            continue
        text = p.get_text(separator=' ').strip()
        text = re.sub(r'\s+', ' ', text)
        if len(text) > 20 and text not in text_blocks:
            text_blocks.append(text)

    cleaned_headings = "\n".join(headings[:15])
    cleaned_content = "\n".join(text_blocks[:30])
    
    page_context = f"Page Title: {title}\nMeta Description: {meta_desc}\n\nHEADINGS:\n{cleaned_headings}\n\nCONTENT:\n{cleaned_content}"
    
    return {
        "url": url,
        "title": title,
        "meta_description": meta_desc,
        "cleaned_text": page_context,
        "raw_html": response.text,
        "headers": dict(response.headers),
        "cookies": dict(response.cookies)
    }

# Advanced multi-page crawler & tech stack signature scanner
def crawl_and_clean_website(url):
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }

    # 1. Fetch Homepage
    homepage_data = fetch_and_clean_page(url, headers)
    if not homepage_data:
        raise Exception(f"Failed to connect to the target website: {url}")

    # 2. Extract internal links from Homepage
    soup = BeautifulSoup(homepage_data["raw_html"], 'html.parser')
    parsed_base = urlparse(url)
    base_domain = parsed_base.netloc.replace('www.', '')

    links = []
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        resolved_url = urljoin(url, href)
        parsed_resolved = urlparse(resolved_url)
        resolved_domain = parsed_resolved.netloc.replace('www.', '')
        
        # Keep only internal links
        if base_domain in resolved_domain or not resolved_domain:
            links.append(resolved_url)

    # 3. Categorize and score subpages to find About, Services, Contact
    dedup_links = list(set(links))
    
    about_candidates = []
    services_candidates = []
    contact_candidates = []

    for l in dedup_links:
        path = urlparse(l).path.lower()
        # Avoid file assets
        if any(path.endswith(ext) for ext in ['.jpg', '.png', '.pdf', '.zip', '.css', '.js']):
            continue
        
        # Scoring path keywords
        if any(kw in path for kw in ['about', 'company', 'who-we-are', 'team', 'story']):
            about_candidates.append(l)
        elif any(kw in path for kw in ['service', 'product', 'solution', 'feature', 'pricing', 'what-we-do']):
            services_candidates.append(l)
        elif any(kw in path for kw in ['contact', 'get-in-touch', 'location', 'reach-us', 'support']):
            contact_candidates.append(l)

    # Pick the single best candidate for each category (avoiding homepage)
    target_subpages = []
    
    # Filter function to avoid duplicates and homepage
    def pick_best(candidates):
        for c in candidates:
            parsed_c = urlparse(c)
            # homepage filter
            if parsed_c.path.strip('/') == '':
                continue
            return c
        return None

    about_url = pick_best(about_candidates)
    services_url = pick_best(services_candidates)
    contact_url = pick_best(contact_candidates)

    if about_url: target_subpages.append(about_url)
    if services_url: target_subpages.append(services_url)
    if contact_url: target_subpages.append(contact_url)

    # Deduplicate subpages
    target_subpages = list(set(target_subpages))

    # 4. Fetch subpages concurrently (ThreadPoolExecutor)
    subpages_data = []
    if target_subpages:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_url = {executor.submit(fetch_and_clean_page, u, headers): u for u in target_subpages}
            for future in concurrent.futures.as_completed(future_to_url):
                res = future.result()
                if res:
                    subpages_data.append(res)

    # 5. Advanced Tech Stack Signature Scanner (Headers, Cookies, HTML, scripts)
    detected_tech = set()
    
    # Analyze all gathered pages and responses
    all_pages = [homepage_data] + subpages_data
    
    for page in all_pages:
        html_lower = page["raw_html"].lower()
        headers_lower = {k.lower(): v.lower() for k, v in page["headers"].items()}
        cookies_lower = {k.lower(): v.lower() for k, v in page["cookies"].items()}

        # -- Hosting / CDN / Servers --
        if 'cloudflare' in headers_lower.get('server', '') or 'cf-ray' in headers_lower:
            detected_tech.add('Cloudflare')
        if 'amazon' in headers_lower.get('server', '') or 'cloudfront' in headers_lower.get('via', ''):
            detected_tech.add('AWS CloudFront / S3')
        if 'vercel' in headers_lower or 'x-vercel-id' in headers_lower:
            detected_tech.add('Vercel')
        if 'netlify' in headers_lower or 'x-nf-request-id' in headers_lower:
            detected_tech.add('Netlify')
        if 'litespeed' in headers_lower.get('server', ''):
            detected_tech.add('LiteSpeed Server')
        if 'apache' in headers_lower.get('server', ''):
            detected_tech.add('Apache HTTP Server')
        if 'nginx' in headers_lower.get('server', ''):
            detected_tech.add('Nginx')
        if 'gunicorn' in headers_lower.get('server', ''):
            detected_tech.add('Gunicorn (Python)')
        
        # -- CMS & E-commerce --
        if 'wp-content' in html_lower or 'wp-includes' in html_lower or 'wordpress' in html_lower:
            detected_tech.add('WordPress')
        if 'w-webflow' in html_lower:
            detected_tech.add('Webflow')
        if 'wix.com' in html_lower or 'wix-image-media' in html_lower:
            detected_tech.add('Wix')
        if 'shopify.com' in html_lower or 'cdn.shopify.com' in html_lower:
            detected_tech.add('Shopify')
        if 'woocommerce' in html_lower or 'wc-' in html_lower:
            detected_tech.add('WooCommerce')
        if 'squarespace' in html_lower:
            detected_tech.add('Squarespace')
            
        # -- Frontend Frameworks & UI Assets --
        if 'react' in html_lower or '_next' in html_lower or 'react-dom' in html_lower:
            detected_tech.add('React')
        if '_next/static' in html_lower or 'nextjs' in html_lower or '__next_data' in html_lower:
            detected_tech.add('Next.js')
        if 'vue.js' in html_lower or 'vuejs' in html_lower or 'v-bind' in html_lower:
            detected_tech.add('Vue.js')
        if 'ng-version' in html_lower or 'angularjs' in html_lower:
            detected_tech.add('Angular')
        if 'tailwindcss' in html_lower or 'tailwind.css' in html_lower:
            detected_tech.add('TailwindCSS')
        if 'bootstrap.min.css' in html_lower or 'bootstrap.min.js' in html_lower:
            detected_tech.add('Bootstrap')
        if 'jquery.min.js' in html_lower or 'jquery-' in html_lower:
            detected_tech.add('jQuery')
        if 'fontawesome' in html_lower or 'fa-' in html_lower:
            detected_tech.add('FontAwesome')
            
        # -- Backends & Engines (via Cookies/Headers) --
        if 'laravel' in html_lower or 'laravel_session' in cookies_lower:
            detected_tech.add('Laravel')
        if 'phpsessid' in cookies_lower or '.php' in html_lower:
            detected_tech.add('PHP')
        if 'jsessionid' in cookies_lower:
            detected_tech.add('Java (J2EE)')
        if 'asp.net_sessionid' in cookies_lower or 'aspsessionid' in cookies_lower:
            detected_tech.add('ASP.NET')
        if 'csrftoken' in cookies_lower and 'django' in html_lower:
            detected_tech.add('Django (Python)')
            
        # -- Analytics & Marketing Tools --
        if 'googletagmanager.com' in html_lower or 'gtag' in html_lower:
            detected_tech.add('Google Tag Manager')
        if 'google-analytics.com' in html_lower or 'ga(' in html_lower:
            detected_tech.add('Google Analytics')
        if 'hotjar' in html_lower:
            detected_tech.add('Hotjar')
        if 'tawk.to' in html_lower or 'crisp.chat' in html_lower or 'js.hs-scripts.com' in html_lower:
            detected_tech.add('Live Chat integration')
        if 'stripe.com' in html_lower:
            detected_tech.add('Stripe Payments')

    # 6. Build the unified structured corpus text
    corpus = f"=== SITE URL: {url} ===\n"
    corpus += f"=== PAGE: Homepage (/) ===\n{homepage_data['cleaned_text']}\n\n"
    
    for page in subpages_data:
        parsed_p = urlparse(page['url'])
        corpus += f"=== PAGE: Subpage ({parsed_p.path}) ===\n{page['cleaned_text']}\n\n"

    # Limit size to stay within context windows and maintain response speed
    if len(corpus) > 25000:
        corpus = corpus[:25000] + "\n...[Content Truncated to avoid context bloom]..."

    return {
        "url": url,
        "title": homepage_data["title"],
        "meta_description": homepage_data["meta_description"],
        "crawled_text": corpus,
        "detected_tech": list(detected_tech),
        "crawled_pages": [homepage_data["url"]] + [p["url"] for p in subpages_data]
    }

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    data = request.json or {}
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400

    api_key = data.get('apiKey') or os.getenv('GEMINI_API_KEY')
    if api_key:
        api_key = api_key.strip("'\" ")
    if not api_key:
        return jsonify({"error": "Gemini API key not found. Please provide it in the UI or set it on the server."}), 400

    try:
        # Step 1: Crawl website (Multi-page concurrent crawler)
        crawled_data = crawl_and_clean_website(url)
    except Exception as e:
        return jsonify({"error": f"Failed to crawl website: {str(e)}"}), 500

    try:
        # Step 2: Configure Gemini API
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        # Construct strictly grounded prompt
        prompt = f"""
You are a senior forensic IT systems architect, business auditor, and technical website cost estimator.
Analyze the following multi-page crawled content from the website: {crawled_data['url']}.

CRAWLED WEBSITE CORPUS DATA:
---
{crawled_data['crawled_text']}
---

Technical Signatures Detected (Headers, Cookies, Scripts, HTML):
{", ".join(crawled_data['detected_tech']) if crawled_data['detected_tech'] else "None detected"}

Provide a comprehensive, professional analysis of this website in JSON format.
Ensure you strictly match the following JSON schema:

{{
  "title": "Refined/Cleaned Website Title or Company Name",
  "description": "Sleek description of what the company does",
  "overview": "Detailed overview of the company, their business domain, core value proposition, and operations.",
  "services": [
    {{
      "name": "Service/Functionality Name",
      "description": "Comprehensive explanation of what this service or feature does based on the content"
    }}
  ],
  "tech_stack": [
    {{
      "category": "Frontend / Backend / CMS / Cloud / Databases / Marketing",
      "technologies": ["Tech 1", "Tech 2"]
    }}
  ],
  "target_audience": {{
    "description": "Summary of target customers",
    "segments": ["Segment 1", "Segment 2"]
  }},
  "cost_estimation": {{
    "currency": "INR",
    "total_estimated_range": "₹X,XX,XXX - ₹Y,XX,XXX (Detailed range in INR)",
    "timeline": "Estimated timeframe to build (e.g., 3-4 months)",
    "breakdown": [
      {{
        "module": "e.g., UI/UX Design, Frontend, Custom Backend APIs, Integration, Testing",
        "cost_range": "e.g. ₹1,00,000 - ₹1,50,000",
        "explanation": "Technical reasoning behind this cost segment based on the complexity found on the site"
      }}
    ]
  }},
  "improvements": [
    {{
      "type": "UI/UX OR Performance OR SEO OR Security",
      "suggestion": "Constructive, actionable critique/recommendation to enhance the site"
    }}
  ],
  "quick_questions": [
    "Suggested question 1",
    "Suggested question 2",
    "Suggested question 3",
    "Suggested question 4"
  ]
}}

CRITICAL GROUNDING RULES:
1. Base your services list, business overview, audience, and stack ONLY on facts explicitly stated or directly implied in the crawled text corpus.
2. If the crawled text does not contain details about a specific field (such as pricing, team size, founding year, or contact address), DO NOT make up details. Write "Not explicitly mentioned in website content" or similar.
3. For the 'tech_stack' classification, list verified technologies we detected ({", ".join(crawled_data['detected_tech'])}) and logically infer other backend/database systems ONLY if standard for the CMS or framework explicitly detected (e.g., if WordPress is detected, PHP and MySQL are factually supported).
4. Be highly realistic and detailed in the 'cost_estimation' breakdown for building a clone/similar system. Make sure the estimates reflect the developer resources, complexity, QA, and project management needed to build a site of this scale.
5. Ensure the output is valid, parsable JSON, and DO NOT wrap it in markdown code blocks like ```json ... ```. Output raw JSON only.
"""

        # Generate content
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        # Parse JSON output
        analysis_result = json.loads(response.text)
        
        # Inject metadata
        analysis_result['url'] = crawled_data['url']
        analysis_result['detected_tech_raw'] = crawled_data['detected_tech']
        analysis_result['crawled_pages'] = crawled_data['crawled_pages']
        
        return jsonify(analysis_result)

    except json.JSONDecodeError as je:
        return jsonify({"error": f"AI model returned invalid JSON structure: {str(je)}", "raw_output": response.text}), 500
    except Exception as e:
        return jsonify({"error": f"AI Generation failed: {str(e)}"}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json or {}
    message = data.get('message')
    history = data.get('history', [])
    website_data = data.get('websiteData', {})
    
    if not message:
        return jsonify({"error": "Message is required"}), 400

    api_key = data.get('apiKey') or os.getenv('GEMINI_API_KEY')
    if api_key:
        api_key = api_key.strip("'\" ")
    if not api_key:
        return jsonify({"error": "Gemini API key not found."}), 400

    try:
        # Configure Gemini API
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        # Format history for prompt context
        history_context = ""
        for msg in history:
            role = "User" if msg.get('role') == 'user' else "Assistant"
            history_context += f"{role}: {msg.get('content')}\n"

        # Construct System Prompts and Site context
        system_instruction = f"""You are a professional, senior IT consultant, software architect, and digital product estimator.
You are discussing a website analysis report with a user. The website in focus is {website_data.get('title', 'this site')} ({website_data.get('url', '')}).

Here is the structured analysis of the website:
- Overview: {website_data.get('overview', 'N/A')}
- Services: {json.dumps(website_data.get('services', []))}
- Tech Stack: {json.dumps(website_data.get('tech_stack', []))}
- Build Cost Range: {website_data.get('cost_estimation', {}).get('total_estimated_range', 'N/A')}
- Breakdown: {json.dumps(website_data.get('cost_estimation', {}).get('breakdown', []))}
- Target Audience: {json.dumps(website_data.get('target_audience', {}))}
- Recommended Improvements: {json.dumps(website_data.get('improvements', []))}

Your goal:
1. Act as a highly consultative expert. Answer questions about how this website functions, how to build a similar product, technical solutions, cost optimizations, and digital strategy.
2. Provide technical, architectural, and financial insights (costs to implement, timelines, required resources).
3. If they ask about costs, break them down clearly or suggest alternatives (e.g. standard CMS vs custom React SPA, cloud host costs, CRM integration).
4. Always maintain a professional, helpful, and technically detailed tone. Keep answers structured with headings and lists where helpful.
5. IMPORTANT: Answer ONLY based on the facts derived from the structured analysis, or clearly label your extensions as general architectural recommendations rather than hard facts about the target site.

Conversation history:
{history_context}
User's latest message: {message}

Assistant response:
"""
        response = model.generate_content(system_instruction)
        return jsonify({"response": response.text})

    except Exception as e:
        return jsonify({"error": f"Chat failed: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    print(f"Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)
