import os
import re
import json
import requests
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from groq import Groq
from urllib.parse import urlparse, urljoin
import concurrent.futures

# Load environment variables
load_dotenv()

# Default Groq model (can be overridden via environment variables)
GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')

app = Flask(__name__, template_folder='templates', static_folder='static')

CORS(app)

# Helper function to crawl a single page and return cleaned text, headers, and soup
def fetch_and_clean_page(url, headers):
    """Fetch a page using requests, falling back to Playwright for JS-heavy content."""
    requests_response = None
    try:
        requests_response = requests.get(url, headers=headers, timeout=8, verify=True)
        requests_response.raise_for_status()
    except Exception:
        # Fallback to HTTP if HTTPS failed
        if url.startswith('https://'):
            http_url = url.replace('https://', 'http://')
            try:
                requests_response = requests.get(http_url, headers=headers, timeout=8, verify=True)
                requests_response.raise_for_status()
            except Exception:
                pass

    # Determine if we should attempt Playwright fallback
    try_playwright = False
    if requests_response is None:
        try_playwright = True
    else:
        # Check if requests got a skeleton page with little/no text
        temp_soup = BeautifulSoup(requests_response.text, 'html.parser')
        # Strip code/formatting tags temporarily to evaluate textual density
        for el in temp_soup(["script", "style", "iframe", "noscript", "svg", "path", "symbol", "canvas"]):
            el.decompose()
        text_content_len = len(temp_soup.get_text().strip())
        
        # If the actual clean text is less than 1200 characters, but raw page has scripts or root divs,
        # it is highly likely a dynamic/client-side rendered app.
        if text_content_len < 1200 and ("<script" in requests_response.text.lower() or "id=\"root\"" in requests_response.text.lower() or "id=\"app\"" in requests_response.text.lower() or "id=\"__next\"" in requests_response.text.lower()):
            try_playwright = True

    response = None
    if try_playwright:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                # Set extra HTTP headers to disable cache and spoof user agent
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    extra_http_headers={
                        'Cache-Control': 'no-cache, no-store, must-revalidate',
                        'Pragma': 'no-cache',
                        'Expires': '0'
                    }
                )
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=18000)
                # Wait an extra 2 seconds for any client-side dynamic content to load/render
                page.wait_for_timeout(2000)
                html = page.content()
                browser.close()
                response = type('Resp', (), {
                    'text': html,
                    'status_code': 200,
                    'headers': {},
                    'cookies': {}
                })
        except Exception:
            pass

    # Fallback to requests if Playwright failed
    if response is None and requests_response is not None:
        response = requests_response

    # If both failed, return None
    if response is None:
        return None

    # Continue with existing cleaning logic using response.text
    soup = BeautifulSoup(response.text, 'html.parser')
    # Get title and meta
    title = soup.title.string.strip() if soup.title else ""
    meta_desc_tag = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
    meta_desc = meta_desc_tag['content'].strip() if meta_desc_tag and meta_desc_tag.has_attr('content') else ""
    # Clean only layout, script, and code-based styling elements
    for element in soup(["script", "style", "iframe", "noscript", "svg", "path", "symbol", "canvas"]):
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
    cleaned_headings = "\n".join(headings[:50])
    cleaned_content = "\n".join(text_blocks[:150])
    page_context = f"Page Title: {title}\nMeta Description: {meta_desc}\n\nHEADINGS:\n{cleaned_headings}\n\nCONTENT:\n{cleaned_content}"
    return {
        "url": url,
        "title": title,
        "meta_description": meta_desc,
        "cleaned_text": page_context,
        "raw_html": response.text,
        "headers": dict(getattr(response, 'headers', {})),
        "cookies": dict(getattr(response, 'cookies', {}))
    }

# Helper function to fetch sitemap URLs
def fetch_sitemap_urls(base_url, headers):
    sitemap_url = urljoin(base_url, '/sitemap.xml')
    try:
        response = requests.get(sitemap_url, headers=headers, timeout=5, verify=True)
        if response.status_code == 200:
            # Extract URLs from sitemap using regex
            loc_urls = re.findall(r'<loc>\s*(https?://[^\s<>]+)\s*</loc>', response.text)
            parsed_base = urlparse(base_url)
            base_domain = parsed_base.netloc.replace('www.', '')
            
            filtered_urls = []
            for u in loc_urls:
                u = u.strip()
                parsed_u = urlparse(u)
                u_domain = parsed_u.netloc.replace('www.', '')
                # Keep internal URLs and ignore non-HTML static files
                if base_domain in u_domain or not u_domain:
                    resolved = urljoin(base_url, u)
                    path = urlparse(resolved).path.lower()
                    if any(path.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.pdf', '.zip', '.css', '.js', '.mp4', '.xml']):
                        continue
                    filtered_urls.append(resolved)
            return list(set(filtered_urls))
    except Exception:
        pass
    return []

# Advanced multi-page crawler & tech stack signature scanner
def crawl_and_clean_website(url, max_pages=15):
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url

    # Configuration constants for crawling depth and performance
    MAX_PAGES_TO_CRAWL = max_pages     # Limit pages to user-selected option
    MAX_WORKERS = min(10, max_pages)   # scale workers accordingly
    MAX_CORPUS_SIZE = 100000   # Adjust corpus size limit for deep scans

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }

    parsed_base = urlparse(url)
    base_domain = parsed_base.netloc.replace('www.', '')

    # Helper to extract internal links from HTML content
    def extract_internal_links(page_url, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        discovered = []
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            resolved = urljoin(page_url, href)
            parsed_resolved = urlparse(resolved)
            resolved_domain = parsed_resolved.netloc.replace('www.', '')
            
            # Keep only internal links and skip common static files
            if base_domain in resolved_domain or not resolved_domain:
                path = parsed_resolved.path.lower()
                if any(path.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.pdf', '.zip', '.css', '.js', '.mp4', '.xml']):
                    continue
                # Normalize URL: strip fragments, queries, and trailing slash
                cleaned_url = resolved.split('#')[0].split('?')[0].rstrip('/')
                if cleaned_url:
                    discovered.append(cleaned_url)
        return list(set(discovered))

    # Helper to calculate priority score based on keywords (lower score is crawled first)
    def get_priority_score(u):
        path = urlparse(u).path.lower()
        priority_keywords = ['about', 'team', 'board', 'leadership', 'ceo', 'founder', 'management', 'executive', 'contact', 'staff', 'people', 'services', 'product', 'pricing', 'features']
        if any(kw in path for kw in priority_keywords):
            return 1
        return 2

    # Try sitemap discovery first
    sitemap_urls = fetch_sitemap_urls(url, headers)
    
    crawled_pages_dict = {}

    if sitemap_urls:
        # We got URLs from the sitemap! Sort by priority
        sitemap_urls = sorted(sitemap_urls, key=get_priority_score)
        
        homepage_cleaned = url.rstrip('/')
        # Remove homepage if it exists in sitemap list to avoid crawling it twice
        sitemap_urls = [u for u in sitemap_urls if u.rstrip('/') != homepage_cleaned]
        
        urls_to_crawl = [url] + sitemap_urls
        urls_to_crawl = list(dict.fromkeys(urls_to_crawl))[:MAX_PAGES_TO_CRAWL]
        
        # Crawl concurrently in thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_url = {executor.submit(fetch_and_clean_page, u, headers): u for u in urls_to_crawl}
            for future in concurrent.futures.as_completed(future_to_url):
                res = future.result()
                if res:
                    crawled_pages_dict[res['url']] = res
    else:
        # Fallback to BFS recursive crawling
        to_crawl_queue = [url.rstrip('/')]
        visited = set()
        
        while to_crawl_queue and len(crawled_pages_dict) < MAX_PAGES_TO_CRAWL:
            # Determine next batch to crawl
            batch_size = min(MAX_WORKERS, MAX_PAGES_TO_CRAWL - len(crawled_pages_dict))
            batch_urls = []
            
            while to_crawl_queue and len(batch_urls) < batch_size:
                u = to_crawl_queue.pop(0)
                if u not in visited:
                    visited.add(u)
                    batch_urls.append(u)
            
            if not batch_urls:
                break
                
            # Crawl batch concurrently
            newly_crawled = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch_urls)) as executor:
                future_to_url = {executor.submit(fetch_and_clean_page, u, headers): u for u in batch_urls}
                for future in concurrent.futures.as_completed(future_to_url):
                    res = future.result()
                    if res:
                        crawled_pages_dict[res['url']] = res
                        newly_crawled.append(res)
            
            # Extract links from successful crawls to enqueue
            new_discovered_links = []
            for page in newly_crawled:
                discovered = extract_internal_links(page['url'], page['raw_html'])
                for d in discovered:
                    if d not in visited and d not in to_crawl_queue and d not in crawled_pages_dict:
                        new_discovered_links.append(d)
            
            # Deduplicate and sort discovered links
            new_discovered_links = list(set(new_discovered_links))
            new_discovered_links = sorted(new_discovered_links, key=get_priority_score)
            
            to_crawl_queue.extend(new_discovered_links)

    # Resolve homepage_data
    homepage_key = None
    for k in crawled_pages_dict.keys():
        parsed_k = urlparse(k)
        if parsed_k.path.strip('/') == '' or k == url or k.rstrip('/') == url.rstrip('/'):
            homepage_key = k
            break
            
    if not homepage_key and crawled_pages_dict:
        homepage_key = list(crawled_pages_dict.keys())[0]
        
    if not crawled_pages_dict:
        # Fallback fetch
        homepage_data = fetch_and_clean_page(url, headers)
        if not homepage_data:
            raise Exception(f"Failed to connect to the target website: {url}")
        crawled_pages_dict[homepage_data['url']] = homepage_data
        homepage_key = homepage_data['url']
        
    homepage_data = crawled_pages_dict[homepage_key]
    subpages_data = [v for k, v in crawled_pages_dict.items() if k != homepage_key]

    # Advanced Tech Stack Signature Scanner (Headers, Cookies, HTML, scripts)
    detected_tech = set()
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

    # Build the unified structured corpus text
    corpus = f"=== SITE URL: {url} ===\n"
    
    # Calculate dynamic character budget per page to stay under LLM token limits (approx 12,000 tokens total)
    num_pages = 1 + len(subpages_data)
    char_budget_per_page = max(3500, 50000 // num_pages)
    
    homepage_text = homepage_data['cleaned_text']
    if len(homepage_text) > char_budget_per_page:
        homepage_text = homepage_text[:char_budget_per_page] + "\n... [TRUNCATED TO FIT TOKEN LIMIT] ..."
        
    corpus += f"=== PAGE: Homepage (/) ===\n{homepage_text}\n\n"
    
    for page in subpages_data:
        parsed_p = urlparse(page['url'])
        page_text = page['cleaned_text']
        if len(page_text) > char_budget_per_page:
            page_text = page_text[:char_budget_per_page] + "\n... [TRUNCATED TO FIT TOKEN LIMIT] ..."
        corpus += f"=== PAGE: Subpage ({parsed_p.path}) ===\n{page_text}\n\n"

    # Chunking logic for large corpuses
    def chunk_text(text, max_len=12000):
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        for p in paragraphs:
            if len(current_chunk) + len(p) < max_len:
                current_chunk += p + "\n\n"
            else:
                chunks.append(current_chunk)
                current_chunk = p + "\n\n"
        chunks.append(current_chunk)
        return chunks

    corpus_chunks = chunk_text(corpus)

    # Extract emails from the corpus
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    emails_found = list(set(re.findall(email_pattern, corpus)))
    
    # Extract CEO name using robust patterns across raw HTML and cleaned text
    ceo_name = None
    all_html = homepage_data['raw_html'] + " ".join([p['raw_html'] for p in subpages_data])
    ceo_patterns = [
        r"CEO[\s\-:]*([A-Z][a-zA-Z.,\-\s]+)",
        r"Chief Executive Officer[\s\-:]*([A-Z][a-zA-Z.,\-\s]+)",
        r"Founder[\s\-:]*([A-Z][a-zA-Z.,\-\s]+)",
        r"President[\s\-:]*([A-Z][a-zA-Z.,\-\s]+)",
        r"Managing Director[\s\-:]*([A-Z][a-zA-Z.,\-\s]+)",
        r"Co-Founder[\s\-:]*([A-Z][a-zA-Z.,\-\s]+)",
        r"([A-Z][a-zA-Z.,\-\s]+)[\s\-]*CEO",
        r"([A-Z][a-zA-Z.,\-\s]+)[\s\-]*Chief Executive Officer",
        r"([A-Z][a-zA-Z.,\-\s]+)[\s\-]*Managing Director"
    ]
    for pat in ceo_patterns:
        match = re.search(pat, all_html, re.IGNORECASE)
        if match:
            ceo_name = match.group(1).strip()
            break
    if not ceo_name:
        for pat in ceo_patterns:
            match = re.search(pat, corpus, re.IGNORECASE)
            if match:
                ceo_name = match.group(1).strip()
                break
    if ceo_name and len(ceo_name) > 100:
        ceo_name = ceo_name[:100].strip()

    return {
        "url": url,
        "title": homepage_data["title"],
        "meta_description": homepage_data["meta_description"],
        "crawled_text": corpus,
        "corpus_chunks": corpus_chunks,
        "detected_tech": list(detected_tech),
        "crawled_pages": [homepage_data["url"]] + [p["url"] for p in subpages_data],
        "emails": emails_found,
        "ceo": ceo_name
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

    max_pages = data.get('maxPages', 15)
    try:
        max_pages = int(max_pages)
        if max_pages < 1:
            max_pages = 1
        elif max_pages > 50:
            max_pages = 50
    except (ValueError, TypeError):
        max_pages = 15

    api_key = data.get('apiKey') or os.getenv('GROQ_API_KEY')
    if api_key:
        api_key = api_key.strip("'\" ")
    if not api_key:
        return jsonify({"error": "Groq API key not found. Please provide it in the UI or set it on the server."}), 400

    try:
        # Step 1: Crawl website (Multi-page concurrent crawler)
        crawled_data = crawl_and_clean_website(url, max_pages=max_pages)
    except Exception as e:
        return jsonify({"error": f"Failed to crawl website: {str(e)}"}), 500

    try:
        # Step 2: Configure Groq API
        client = Groq(api_key=api_key)

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
        "ceo": "CEO name if mentioned",
        "title": "Refined/Cleaned Website Title or Company Name",
        "description": "Sleek description of what the company does",
        "overview": "Detailed overview of the company, their business domain, core value proposition, and operations.",
        "company_info": {{
            "leadership": "Names and roles of key personnel (e.g. CEO, founders) if mentioned",
            "contact": "Email, phone, or location if mentioned",
            "founded": "Year founded if mentioned"
        }},
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

        # Generate content with Groq JSON mode
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model=GROQ_MODEL,
            response_format={"type": "json_object"}
        )
        
        # Extract response text
        response_text = chat_completion.choices[0].message.content if chat_completion.choices else ""
        if not response_text or not response_text.strip():
            return jsonify({"error": "AI model returned empty response. Please try again or check the prompt."}), 500
        
        # Parse JSON output
        analysis_result = json.loads(response_text)
        
        # Inject metadata
        analysis_result['url'] = crawled_data['url']
        analysis_result['detected_tech_raw'] = crawled_data['detected_tech']
        analysis_result['crawled_pages'] = crawled_data['crawled_pages']
        analysis_result['emails'] = crawled_data.get('emails', [])
        
        return jsonify(analysis_result)

    except json.JSONDecodeError as je:
        return jsonify({"error": f"AI model returned invalid JSON structure: {str(je)}", "raw_output": response_text}), 500
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

    api_key = data.get('apiKey') or os.getenv('GROQ_API_KEY')
    if api_key:
        api_key = api_key.strip("'\" ")
    if not api_key:
        return jsonify({"error": "Groq API key not found."}), 400

    try:
        # Configure Groq API
        client = Groq(api_key=api_key)

        # Construct System Prompts and Site context
        system_instruction = f"""You are a professional, senior IT consultant, software architect, and digital product estimator.
You are discussing a website analysis report with a user. The website in focus is {website_data.get('title', 'this site')} ({website_data.get('url', '')}).

Here is the structured analysis of the website:
- Overview: {website_data.get('overview', 'N/A')}
- Company Info & Leadership: {json.dumps(website_data.get('company_info', {}))}
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
"""
        messages = [{"role": "system", "content": system_instruction}]
        
        # Populate history dynamically, mapping roles correctly for OpenAI format compatibility
        for msg in history:
            role = msg.get('role')
            if role not in ['system', 'user', 'assistant']:
                role = 'user' if role == 'user' else 'assistant'
            messages.append({"role": role, "content": msg.get('content')})
            
        messages.append({"role": "user", "content": message})

        chat_completion = client.chat.completions.create(
            messages=messages,
            model=GROQ_MODEL
        )
        
        return jsonify({"response": chat_completion.choices[0].message.content})

    except Exception as e:
        return jsonify({"error": f"Chat failed: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    print(f"Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)
