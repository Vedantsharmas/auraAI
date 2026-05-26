import os
import re
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# Helper function to crawl and extract clean text from a website
def crawl_and_clean_website(url):
    # Ensure URL has a scheme
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }

    try:
        response = requests.get(url, headers=headers, timeout=12, verify=True)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        # Fallback to HTTP if HTTPS failed, or raise
        if url.startswith('https://'):
            http_url = url.replace('https://', 'http://')
            try:
                response = requests.get(http_url, headers=headers, timeout=10, verify=True)
                response.raise_for_status()
            except requests.exceptions.RequestException as err:
                raise Exception(f"Failed to connect to the website: {str(err)}")
        else:
            raise Exception(f"Failed to connect to the website: {str(e)}")

    soup = BeautifulSoup(response.text, 'html.parser')

    # Get title and meta description
    title = soup.title.string.strip() if soup.title else ""
    
    meta_desc_tag = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
    meta_desc = meta_desc_tag['content'].strip() if meta_desc_tag and meta_desc_tag.has_attr('content') else ""

    # Clean up scripts, styles, iframe, and layout elements
    for element in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript", "svg", "path", "symbol", "canvas"]):
        element.decompose()

    # Get headings
    headings = []
    for tag in ['h1', 'h2', 'h3', 'h4']:
        for h in soup.find_all(tag):
            text = h.get_text().strip()
            if text and len(text) > 3:
                headings.append(f"{tag.upper()}: {text}")

    # Extract all text blocks
    text_blocks = []
    for p in soup.find_all(['p', 'li', 'article', 'section', 'td', 'div']):
        # Avoid nested duplicate texts
        if p.name == 'div' and p.find(['p', 'li', 'article', 'section']):
            continue
        text = p.get_text(separator=' ').strip()
        # Clean multiple spaces/newlines
        text = re.sub(r'\s+', ' ', text)
        if len(text) > 20 and text not in text_blocks:
            text_blocks.append(text)

    # Combine data
    cleaned_headings = "\n".join(headings[:25])
    cleaned_content = "\n".join(text_blocks[:45])
    
    # Cap total character size to prevent token bloating while maintaining rich content
    combined_context = f"Website Title: {title}\nMeta Description: {meta_desc}\n\nHEADINGS:\n{cleaned_headings}\n\nCONTENT SEGMENTS:\n{cleaned_content}"
    if len(combined_context) > 15000:
        combined_context = combined_context[:15000] + "\n...[Content Truncated for Analysis]..."

    # Detect basic tech stack indicators from the HTML
    detected_tech = []
    html_str = response.text.lower()
    
    tech_patterns = {
        'WordPress': ['wp-content', 'wp-includes', 'wordpress'],
        'React': ['react', '_next', 'root', 'react-dom'],
        'Next.js': ['_next/static', 'nextjs', '__next_data'],
        'Vue.js': ['vue.js', 'vuejs', 'v-bind', 'v-model'],
        'Angular': ['ng-version', 'angularjs', 'ng-app'],
        'Laravel': ['laravel', 'csrf-token'],
        'Shopify': ['shopify.com', 'cdn.shopify.com', 'shopify-payment-button'],
        'TailwindCSS': ['tailwindcss', 'tailwind'],
        'Bootstrap': ['bootstrap.min.css', 'bootstrap.min.js', 'bootstrap-css'],
        'jQuery': ['jquery.min.js', 'jquery-'],
        'Webflow': ['w-webflow', 'webflow.css'],
        'Wix': ['wix.com', 'wix-image-media-link'],
        'PHP': ['.php', 'phpsessid']
    }
    
    for tech, patterns in tech_patterns.items():
        if any(pat in html_str for pat in patterns):
            detected_tech.append(tech)

    return {
        "url": url,
        "title": title,
        "meta_description": meta_desc,
        "crawled_text": combined_context,
        "detected_tech": detected_tech
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

    # Get API key (first check request payload, then .env)
    api_key = data.get('apiKey') or os.getenv('GEMINI_API_KEY')
    if api_key:
        api_key = api_key.strip("'\" ")
    if not api_key:
        return jsonify({"error": "Gemini API key not found. Please provide it in the UI or set it on the server."}), 400

    try:
        # Step 1: Crawl website
        crawled_data = crawl_and_clean_website(url)
    except Exception as e:
        return jsonify({"error": f"Failed to crawl website: {str(e)}"}), 500

    try:
        # Step 2: Configure Gemini API
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        # Construct prompt
        prompt = f"""
You are a world-class IT systems architect, business analyst, and website cost estimator.
Analyze the following crawled web content from the website: {crawled_data['url']}.

Website Details:
- Title: {crawled_data['title']}
- Meta Description: {crawled_data['meta_description']}
- Technical Indicators Detected: {", ".join(crawled_data['detected_tech']) if crawled_data['detected_tech'] else "None detected"}

Crawled Page Content:
---
{crawled_data['crawled_text']}
---

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

Guidelines:
1. Base your services list, audience, and stack on the actual crawled content, combining it with logical industry practices for similar businesses.
2. In 'tech_stack', list technologies we detected ({", ".join(crawled_data['detected_tech'])}) and infer likely others (e.g. Node.js/Python, MySQL/PostgreSQL, AWS/GCP, Google Analytics) to provide a complete production stack.
3. Be highly realistic and detailed in the 'cost_estimation' breakdown. Make sure the estimates reflect the developer resources, complexity, QA, and project management needed to clone or build a similar site/service.
4. Ensure the output is valid, parsable JSON, and DO NOT wrap it in markdown code blocks like ```json ... ```. Output raw JSON only.
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
    port = int(os.getenv('PORT', 5000))
    print(f"Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)
