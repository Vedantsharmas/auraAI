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

# Global flag to track if Playwright can be successfully spawned
PLAYWRIGHT_AVAILABLE = True

app = Flask(__name__, template_folder='templates', static_folder='static')

CORS(app)

# Helper function to fetch a single page using requests.
def fetch_page_requests(url, headers):
    """Fetch a single page using requests. Returns tuple (html, headers, cookies, status_code)."""
    try:
        response = requests.get(url, headers=headers, timeout=8, verify=True)
        return response.text, dict(response.headers), dict(response.cookies), response.status_code
    except Exception:
        # Fallback to HTTP if HTTPS failed
        if url.startswith('https://'):
            http_url = url.replace('https://', 'http://')
            try:
                response = requests.get(http_url, headers=headers, timeout=8, verify=True)
                return response.text, dict(response.headers), dict(response.cookies), response.status_code
            except Exception:
                pass
    return None, {}, {}, None

# Helper function to fetch a batch of URLs using a single Playwright instance sequentially.
def fetch_pages_playwright(urls, headers):
    """Fetch a list of URLs sequentially using a single Playwright browser instance."""
    global PLAYWRIGHT_AVAILABLE
    results = {}
    if not urls or not PLAYWRIGHT_AVAILABLE:
        return results

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as launch_err:
                print(f"Severe error: Failed to launch Playwright browser: {launch_err}")
                PLAYWRIGHT_AVAILABLE = False
                return results

            # Create a single context with realistic browser settings
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                extra_http_headers={
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            )
            context.set_default_navigation_timeout(15000)
            
            for url in urls:
                try:
                    page = context.new_page()
                    # Use wait_until="networkidle" for better SPA loading
                    response = page.goto(url, wait_until="networkidle", timeout=15000)
                    # Wait a bit for dynamic content to render
                    page.wait_for_timeout(1500)
                    html = page.content()
                    
                    resp_headers = {}
                    if response:
                        resp_headers = dict(response.headers)
                    resp_cookies = {}
                    for cookie in context.cookies([url]):
                        resp_cookies[cookie['name']] = cookie['value']
                        
                    results[url] = (html, resp_headers, resp_cookies, 200)
                    page.close()
                except Exception as e:
                    print(f"Playwright failed to fetch {url}: {e}")
                    results[url] = (None, {}, {}, None)
            
            browser.close()
    except Exception as e:
        print(f"Failed to run Playwright session: {e}")
    return results

# Helper function to clean page HTML content into text, title, meta etc.
def clean_page_content(url, html_content, headers, cookies):
    soup = BeautifulSoup(html_content, 'html.parser')
    # Get title and meta
    title = soup.title.string.strip() if soup.title else ""
    meta_desc_tag = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
    meta_desc = meta_desc_tag['content'].strip() if meta_desc_tag and meta_desc_tag.has_attr('content') else ""

    # Extract structured contact info BEFORE decomposing elements (since anchors can have mailto/tel hrefs)
    contact_emails = set()
    contact_phones = set()
    
    # 1. Check mailto: and tel: links
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if href.lower().startswith('mailto:'):
            email = href[7:].split('?')[0].strip()
            if email:
                contact_emails.add(email)
        elif href.lower().startswith('tel:'):
            phone = href[4:].split('?')[0].strip()
            if phone:
                contact_phones.add(phone)

    # 2. Check plain text in the soup
    page_text = soup.get_text()
    for email in re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", page_text):
        contact_emails.add(email.strip())
        
    for phone in re.findall(r"\+?\d{1,4}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}", page_text):
        digits = re.sub(r"\D", "", phone)
        if 7 <= len(digits) <= 15:
            contact_phones.add(phone.strip())

    # Clean layout, script, and code-based styling elements
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
        if not text:
            continue

        # Preserve short items if they look like valuable contact details
        is_contact_detail = False
        text_lower = text.lower()
        if "@" in text and re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text):
            is_contact_detail = True
        elif re.search(r"\+?\d{1,4}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}", text):
            digits = re.sub(r"\D", "", text)
            if 7 <= len(digits) <= 15:
                is_contact_detail = True
        elif any(kw in text_lower for kw in ["address", "office", "hq", "headquarter", "street", "road", "building", "floor", "highway", "avenue", "lane", "pin code", "zip code", "contact us", "call us", "phone", "email"]):
            is_contact_detail = True

        if (len(text) > 20 or is_contact_detail) and text not in text_blocks:
            text_blocks.append(text)

    cleaned_headings = "\n".join(headings[:50])
    cleaned_content = "\n".join(text_blocks[:150])
    
    # Format contact section
    contact_info_lines = []
    if contact_emails:
        contact_info_lines.append(f"Emails found: {', '.join(sorted(contact_emails))}")
    if contact_phones:
        contact_info_lines.append(f"Phones found: {', '.join(sorted(contact_phones))}")
    contact_summary = "\n".join(contact_info_lines) if contact_info_lines else "None extracted"

    page_context = f"Page Title: {title}\nMeta Description: {meta_desc}\n\nHEADINGS:\n{cleaned_headings}\n\nCONTENT:\n{cleaned_content}\n\nEXTRACTED CONTACT INFO:\n{contact_summary}"
    
    return {
        "url": url,
        "title": title,
        "meta_description": meta_desc,
        "cleaned_text": page_context,
        "raw_html": html_content,
        "headers": headers,
        "cookies": cookies
    }

# Optimized standalone fetch function (keeps backward compatibility)
def fetch_and_clean_page(url, headers):
    """Fetch a single page using requests, falling back to Playwright for JS-heavy content (optimized)."""
    html, resp_headers, resp_cookies, status_code = fetch_page_requests(url, headers)
    
    try_playwright = False
    if html is None or status_code != 200:
        try_playwright = True
    else:
        temp_soup = BeautifulSoup(html, 'html.parser')
        for el in temp_soup(["script", "style", "iframe", "noscript", "svg", "path", "symbol", "canvas"]):
            el.decompose()
        text_content_len = len(temp_soup.get_text().strip())
        
        # Enhanced SPA detection - look for React/Vue/Angular indicators
        is_spa = False
        html_lower = html.lower()
        if ('id="root"' in html_lower or 
            'id="app"' in html_lower or 
            'id="__next"' in html_lower or 
            'data-reactroot' in html_lower or
            'ng-version' in html_lower or
            'vue-app' in html_lower or
            text_content_len < 800):
            is_spa = True
        
        # If it's an SPA with low text content, use Playwright
        if is_spa and text_content_len < 1000:
            try_playwright = True

    if try_playwright:
        pw_results = fetch_pages_playwright([url], headers)
        if url in pw_results and pw_results[url][0] is not None:
            html, resp_headers, resp_cookies, _ = pw_results[url]

    if html is None:
        return None

    return clean_page_content(url, html, resp_headers, resp_cookies)


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


def extract_ceo_from_js_bundle(base_url, headers):
    """Fetch and parse the main JS bundle to extract CEO/leadership information."""
    try:
        # First fetch the homepage to find the JS bundle URL
        resp = requests.get(base_url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return None
        
        # Look for the main JS bundle in the HTML
        js_patterns = [
            r'static/js/main\.[a-f0-9]+\.js',
            r'static/js/bundle\.js',
            r'static/js/[^"]+\.js',
            r'js/main\.[a-f0-9]+\.js'
        ]
        
        js_url = None
        for pattern in js_patterns:
            matches = re.findall(pattern, resp.text)
            if matches:
                js_url = matches[0]
                break
        
        if not js_url:
            return None
        
        # Fetch the JS bundle
        full_js_url = urljoin(base_url, js_url)
        js_resp = requests.get(full_js_url, headers=headers, timeout=15)
        if js_resp.status_code != 200:
            return None
        
        js_content = js_resp.text
        
        # Enhanced CEO extraction patterns
        ceo_patterns = [
            # Pattern for team array in the JS
            r'name:\s*["\']([^"\']+)["\'].*?position:\s*["\'][^"\']*CEO[^"\']*["\']',
            r'position:\s*["\'][^"\']*CEO[^"\']*["\'].*?name:\s*["\']([^"\']+)["\']',
            r'"name":"([^"]+)".*?"position":"[^"]*CEO[^"]*"',
            r'"position":"[^"]*CEO[^"]*".*?"name":"([^"]+)"',
            # CEO name patterns
            r'CEO[\s\-:]*([A-Z][a-zA-Z.,\-\s]+)',
            r'Chief Executive Officer[\s\-:]*([A-Z][a-zA-Z.,\-\s]+)',
            r'Founder[\s\-:]*([A-Z][a-zA-Z.,\-\s]+)',
            r'([A-Z][a-zA-Z.,\-\s]+)[\s\-]*CEO',
            r'([A-Z][a-zA-Z.,\-\s]+)[\s\-]*Chief Executive Officer',
            # Specific known names from the site
            r'Bharat\s+Desai',
            r'Manish\s+Shah',
            r'Jay\s+shah',
            r'Heer\s+patel',
            r'Dhaval\s+prajapati',
            r'Mihir\s+prajapati'
        ]
        
        for pattern in ceo_patterns:
            match = re.search(pattern, js_content, re.IGNORECASE)
            if match:
                ceo_name = match.group(1).strip()
                # Clean up the name
                ceo_name = re.sub(r'[^\w\s\.\-]', '', ceo_name)
                if len(ceo_name) > 3 and len(ceo_name) < 100:
                    return ceo_name
    except Exception as e:
        print(f"Error extracting CEO from JS bundle: {e}")
    
    return None


# Enhanced internal link extraction for SPAs
def extract_internal_links_enhanced(page_url, html_content, base_domain):
    """Extract internal links from HTML, including React Router links."""
    soup = BeautifulSoup(html_content, 'html.parser')
    discovered = []
    
    # Look for standard href links
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if href and not href.startswith('#') and not href.startswith('javascript:'):
            resolved = urljoin(page_url, href)
            parsed_resolved = urlparse(resolved)
            resolved_domain = parsed_resolved.netloc.replace('www.', '')
            
            # Keep only internal links
            if base_domain in resolved_domain or not resolved_domain:
                path = parsed_resolved.path.lower()
                # Skip static files
                if any(path.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.pdf', '.zip', '.css', '.js', '.mp4', '.xml', '.svg', '.ico', '.webp']):
                    continue
                # Normalize URL
                cleaned_url = resolved.split('#')[0].split('?')[0].rstrip('/')
                if cleaned_url and cleaned_url not in discovered:
                    discovered.append(cleaned_url)
    
    # Also look for React Router links (data-to, data-href, onClick navigate)
    react_link_selectors = ['[data-to]', '[data-href]', '[data-path]', '[data-url]', '[to]']
    for selector in react_link_selectors:
        for elem in soup.select(selector):
            href = elem.get('data-to') or elem.get('data-href') or elem.get('data-path') or elem.get('data-url') or elem.get('to')
            if href and isinstance(href, str) and href.strip():
                href = href.strip()
                if not href.startswith('#') and not href.startswith('javascript:'):
                    resolved = urljoin(page_url, href)
                    parsed_resolved = urlparse(resolved)
                    resolved_domain = parsed_resolved.netloc.replace('www.', '')
                    
                    if base_domain in resolved_domain or not resolved_domain:
                        cleaned_url = resolved.split('#')[0].split('?')[0].rstrip('/')
                        if cleaned_url and cleaned_url not in discovered:
                            discovered.append(cleaned_url)
    
    return discovered


# Advanced multi-page crawler & tech stack signature scanner
def crawl_and_clean_website(url, max_pages=15):
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url

    # Configuration constants for crawling depth and performance
    MAX_PAGES_TO_CRAWL = max_pages
    MAX_WORKERS = min(10, max_pages)
    MAX_CORPUS_SIZE = 100000

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
    root_homepage = f"{parsed_base.scheme}://{parsed_base.netloc}"
    
    # Pre-defined important routes to crawl for SPAs
    important_routes = ['/who-we-are', '/our-services', '/about', '/team', '/contact', '/about-us', '/company', '/leadership']
    
    # Seed queue with homepage and important routes
    to_crawl_queue = [url.rstrip('/')]
    
    # Add root homepage
    root_cleaned = root_homepage.rstrip('/')
    if root_cleaned not in to_crawl_queue:
        to_crawl_queue.append(root_cleaned)
    
    # Add important routes
    for route in important_routes:
        full_url = urljoin(root_homepage, route)
        cleaned = full_url.rstrip('/')
        if cleaned not in to_crawl_queue:
            to_crawl_queue.append(cleaned)
    
    # Add sitemap URLs
    sitemap_urls = fetch_sitemap_urls(root_homepage, headers)
    for s_url in sitemap_urls:
        s_url_cleaned = s_url.rstrip('/')
        if s_url_cleaned not in to_crawl_queue:
            to_crawl_queue.append(s_url_cleaned)
    
    # Priority scoring for crawling order
    def get_priority_score(u):
        parsed_u = urlparse(u)
        path = parsed_u.path.lower()
        if path.strip('/') == '':
            return 0
        priority_keywords = ['who-we-are', 'about', 'team', 'leadership', 'ceo', 'founder', 'management', 'executive', 'contact', 'staff', 'people']
        if any(kw in path for kw in priority_keywords):
            return 1
        return 2
    
    # Sort initial queue by priority
    to_crawl_queue = sorted(list(dict.fromkeys(to_crawl_queue)), key=get_priority_score)
    
    crawled_pages_dict = {}
    visited = set()
    
    # Check if it's an SPA on first page
    is_spa_site = False
    
    while to_crawl_queue and len(crawled_pages_dict) < MAX_PAGES_TO_CRAWL:
        # Determine next batch to crawl
        batch_size = min(MAX_WORKERS, MAX_PAGES_TO_CRAWL - len(crawled_pages_dict))
        batch_urls = []
        
        while to_crawl_queue and len(batch_urls) < batch_size:
            u = to_crawl_queue.pop(0)
            u_cleaned = u.rstrip('/')
            if u_cleaned not in visited:
                visited.add(u_cleaned)
                batch_urls.append(u_cleaned)
        
        if not batch_urls:
            break
        
        # First, try requests for all URLs
        requests_results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch_urls)) as executor:
            future_to_url = {executor.submit(fetch_page_requests, u, headers): u for u in batch_urls}
            for future in concurrent.futures.as_completed(future_to_url):
                u = future_to_url[future]
                try:
                    html, r_headers, r_cookies, status_code = future.result()
                    requests_results[u] = (html, r_headers, r_cookies, status_code)
                except Exception as e:
                    print(f"Requests failed for {u} in batch: {e}")
                    requests_results[u] = (None, {}, {}, None)
        
        # Determine which URLs need Playwright fallback
        playwright_urls = []
        crawled_this_batch = []
        
        for u in batch_urls:
            html, r_headers, r_cookies, status_code = requests_results.get(u, (None, {}, {}, None))
            
            try_playwright = False
            
            # Check if this is the first page to detect SPA
            if u == root_cleaned or u == url.rstrip('/'):
                if html and len(html) > 0:
                    html_lower = html.lower()
                    if ('id="root"' in html_lower or 
                        'id="app"' in html_lower or 
                        'id="__next"' in html_lower or
                        'ng-version' in html_lower or
                        'data-reactroot' in html_lower):
                        is_spa_site = True
                        print(f"Detected SPA site: {u}")
            
            if html is None or status_code != 200:
                try_playwright = True
            else:
                temp_soup = BeautifulSoup(html, 'html.parser')
                for el in temp_soup(["script", "style", "iframe", "noscript", "svg", "path", "symbol", "canvas"]):
                    el.decompose()
                text_content_len = len(temp_soup.get_text().strip())
                
                # For SPA sites, always use Playwright for navigation pages
                if is_spa_site and u != root_cleaned:
                    try_playwright = True
                # Otherwise, check if content is too sparse
                elif text_content_len < 600 and (
                    "id=\"root\"" in html.lower() or 
                    "id=\"app\"" in html.lower() or 
                    "id=\"__next\"" in html.lower() or 
                    "window.__next_data" in html.lower() or
                    "<script" in html.lower()
                ):
                    try_playwright = True
            
            if try_playwright:
                playwright_urls.append(u)
            else:
                # Succeeded with requests, clean immediately
                cleaned = clean_page_content(u, html, r_headers, r_cookies)
                crawled_pages_dict[u] = cleaned
                crawled_this_batch.append(cleaned)
        
        # Fetch all Playwright URLs using a single browser instance
        if playwright_urls:
            pw_results = fetch_pages_playwright(playwright_urls, headers)
            for u in playwright_urls:
                html, pw_headers, pw_cookies, status_code = pw_results.get(u, (None, {}, {}, None))
                if html is not None:
                    cleaned = clean_page_content(u, html, pw_headers, pw_cookies)
                    crawled_pages_dict[u] = cleaned
                    crawled_this_batch.append(cleaned)
                else:
                    # Fallback to requests result if available
                    req_html, req_headers, req_cookies, req_status = requests_results.get(u, (None, {}, {}, None))
                    if req_html is not None:
                        cleaned = clean_page_content(u, req_html, req_headers, req_cookies)
                        crawled_pages_dict[u] = cleaned
                        crawled_this_batch.append(cleaned)
        
        newly_crawled = crawled_this_batch
        
        # Extract links from successful crawls using enhanced method
        new_discovered_links = []
        for page in newly_crawled:
            discovered = extract_internal_links_enhanced(page['url'], page['raw_html'], base_domain)
            for d in discovered:
                d_cleaned = d.rstrip('/')
                if d_cleaned not in visited and d_cleaned not in to_crawl_queue and d_cleaned not in crawled_pages_dict:
                    new_discovered_links.append(d_cleaned)
        
        # Deduplicate and sort discovered links
        new_discovered_links = list(set(new_discovered_links))
        new_discovered_links = sorted(new_discovered_links, key=get_priority_score)
        
        to_crawl_queue.extend(new_discovered_links)

    # Resolve homepage_data
    homepage_key = None
    for k in crawled_pages_dict.keys():
        parsed_k = urlparse(k)
        if parsed_k.path.strip('/') == '':
            homepage_key = k
            break
    
    if not homepage_key:
        for k in crawled_pages_dict.keys():
            if k == url or k.rstrip('/') == url.rstrip('/'):
                homepage_key = k
                break
    
    if not homepage_key and crawled_pages_dict:
        homepage_key = list(crawled_pages_dict.keys())[0]
    
    if not crawled_pages_dict:
        # Fallback fetch with Playwright for SPA
        print(f"Warning: No pages crawled with requests, using Playwright for {url}")
        pw_results = fetch_pages_playwright([url], headers)
        if url in pw_results and pw_results[url][0] is not None:
            html, pw_headers, pw_cookies, _ = pw_results[url]
            homepage_data = clean_page_content(url, html, pw_headers, pw_cookies)
            crawled_pages_dict[homepage_data['url']] = homepage_data
            homepage_key = homepage_data['url']
        else:
            raise Exception(f"Failed to connect to the target website: {url}")
    
    homepage_data = crawled_pages_dict[homepage_key]
    
    # Unique values from crawled_pages_dict
    unique_pages = list({v['url']: v for v in crawled_pages_dict.values()}.values())
    subpages_data = [p for p in unique_pages if p['url'] != homepage_key]

    # Advanced Tech Stack Signature Scanner
    detected_tech = set()
    all_pages = [homepage_data] + subpages_data
    
    for page in all_pages:
        html_lower = page["raw_html"].lower()
        headers_lower = {k.lower(): v.lower() for k, v in page["headers"].items()}
        cookies_lower = {k.lower(): v.lower() for k, v in page["cookies"].items()}

        # Hosting / CDN / Servers
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
        
        # CMS & E-commerce
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
            
        # Frontend Frameworks & UI Assets
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
            
        # Backends & Engines
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
            
        # Analytics & Marketing Tools
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

    # Build unified structured corpus text
    corpus = f"=== SITE URL: {url} ===\n"
    
    # Cap subpages sent to LLM
    subpages_for_llm = subpages_data[:9]
    num_pages = 1 + len(subpages_for_llm)
    
    char_budget_per_page = max(800, 14000 // num_pages)
    
    homepage_text = homepage_data['cleaned_text']
    if len(homepage_text) > char_budget_per_page:
        homepage_text = homepage_text[:char_budget_per_page] + "\n... [TRUNCATED TO FIT TOKEN LIMIT] ..."
        
    corpus += f"=== PAGE: Homepage (/) ===\n{homepage_text}\n\n"
    
    for page in subpages_for_llm:
        parsed_p = urlparse(page['url'])
        page_text = page['cleaned_text']
        if len(page_text) > char_budget_per_page:
            page_text = page_text[:char_budget_per_page] + "\n... [TRUNCATED TO FIT TOKEN LIMIT] ..."
        corpus += f"=== PAGE: Subpage ({parsed_p.path}) ===\n{page_text}\n\n"

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
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    corpus_chunks = chunk_text(corpus)

    # Extract emails from the corpus
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    emails_found = list(set(re.findall(email_pattern, corpus)))
    
    # Extract CEO name - try multiple methods
    ceo_name = None
    
    # Method 1: Extract from crawled pages (existing method)
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
    
    # Method 2: If not found, try from JS bundle
    if not ceo_name or len(ceo_name) < 3:
        js_ceo = extract_ceo_from_js_bundle(root_homepage, headers)
        if js_ceo:
            ceo_name = js_ceo
    
    # Method 3: Search in corpus
    if not ceo_name or len(ceo_name) < 3:
        for pat in ceo_patterns:
            match = re.search(pat, corpus, re.IGNORECASE)
            if match:
                ceo_name = match.group(1).strip()
                break
    
    # Clean up CEO name
    if ceo_name:
        ceo_name = re.sub(r'[^\w\s\.\-]', '', ceo_name)
        if len(ceo_name) > 100:
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

        # Construct strictly grounded prompt with CEO info if available
        ceo_info = f"CEO/Founder: {crawled_data['ceo']}" if crawled_data.get('ceo') else "CEO/Founder: Not explicitly mentioned"
        
        prompt = f"""
You are a senior forensic IT systems architect, business auditor, and technical website cost estimator.
Analyze the following multi-page crawled content from the website: {crawled_data['url']}.

CRAWLED WEBSITE CORPUS DATA:
---
{crawled_data['crawled_text']}
---

Technical Signatures Detected (Headers, Cookies, Scripts, HTML):
{", ".join(crawled_data['detected_tech']) if crawled_data['detected_tech'] else "None detected"}

Leadership Information: {ceo_info}

Provide a comprehensive, professional analysis of this website in JSON format.
Ensure you strictly match the following JSON schema:

{{
        "ceo": "CEO name if mentioned - use the leadership information provided or extract from content",
        "title": "Refined/Cleaned Website Title or Company Name",
        "description": "Sleek description of what the company does",
        "overview": "Detailed overview of the company, their business domain, core value proposition, and operations.",
        "company_info": {{
            "owner": "Names of founders, owners, or CEO if mentioned (or 'Not explicitly mentioned in website content')",
            "location": "HQ city/state/country if mentioned (or 'Not explicitly mentioned in website content')",
            "address": "Full physical address(es) if mentioned (or 'Not explicitly mentioned in website content')",
            "contact_details": {{
                "email": "Primary contact email address if mentioned (or 'Not explicitly mentioned in website content')",
                "phone": "Primary phone number if mentioned (or 'Not explicitly mentioned in website content')"
            }},
            "founded": "Year founded if mentioned (or 'Not explicitly mentioned in website content')",
            "core_industry": "Primary industry or domain of operation (e.g. EdTech, FinTech, E-commerce, Software Development, IT Consulting, etc.)"
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
3. For the 'tech_stack' classification, list verified technologies we detected ({", ".join(crawled_data['detected_tech'])}) and logically infer other backend/database systems ONLY if standard for the CMS or framework explicitly detected.
4. Be highly realistic and detailed in the 'cost_estimation' breakdown for building a clone/similar system.
5. IMPORTANT: Use the leadership information provided to identify the CEO. The CEO name is {crawled_data.get('ceo') or 'to be extracted from content'}.
6. Ensure the output is valid, parsable JSON, and DO NOT wrap it in markdown code blocks like ```json ... ```. Output raw JSON only.
"""

        # Generate content with Groq JSON mode
        load_dotenv()
        model_to_use = data.get('model') or os.getenv('GROQ_MODEL') or 'llama-3.1-8b-instant'
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model=model_to_use,
                response_format={"type": "json_object"}
            )
        except Exception as e:
            if "429" in str(e) and model_to_use != 'llama-3.1-8b-instant':
                print(f"Model {model_to_use} rate limited. Falling back to llama-3.1-8b-instant...")
                model_to_use = 'llama-3.1-8b-instant'
                chat_completion = client.chat.completions.create(
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    model=model_to_use,
                    response_format={"type": "json_object"}
                )
            else:
                raise e
        
        # Extract response text
        response_text = chat_completion.choices[0].message.content if chat_completion.choices else ""
        if not response_text or not response_text.strip():
            return jsonify({"error": "AI model returned empty response. Please try again or check the prompt."}), 500
        
        # Parse JSON output
        analysis_result = json.loads(response_text)
        
        # Inject metadata and ensure CEO is set correctly
        analysis_result['url'] = crawled_data['url']
        analysis_result['detected_tech_raw'] = crawled_data['detected_tech']
        analysis_result['crawled_pages'] = crawled_data['crawled_pages']
        analysis_result['emails'] = crawled_data.get('emails', [])
        
        # Ensure CEO is set from crawled data if not in AI response
        if crawled_data.get('ceo') and (not analysis_result.get('ceo') or analysis_result.get('ceo') == 'Not explicitly mentioned in website content'):
            analysis_result['ceo'] = crawled_data['ceo']
            if 'company_info' in analysis_result and 'owner' in analysis_result['company_info']:
                if analysis_result['company_info']['owner'] == 'Not explicitly mentioned in website content':
                    analysis_result['company_info']['owner'] = crawled_data['ceo']
        
        return jsonify(analysis_result)

    except json.JSONDecodeError as je:
        return jsonify({"error": f"AI model returned invalid JSON structure: {str(je)}", "raw_output": response_text if 'response_text' in locals() else ""}), 500
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
        client = Groq(api_key=api_key)

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
3. If they ask about costs, break them down clearly or suggest alternatives.
4. Always maintain a professional, helpful, and technically detailed tone.
5. IMPORTANT: Answer ONLY based on the facts derived from the structured analysis.
"""
        messages = [{"role": "system", "content": system_instruction}]
        
        for msg in history:
            role = msg.get('role')
            if role not in ['system', 'user', 'assistant']:
                role = 'user' if role == 'user' else 'assistant'
            messages.append({"role": role, "content": msg.get('content')})
            
        messages.append({"role": "user", "content": message})

        load_dotenv()
        model_to_use = data.get('model') or os.getenv('GROQ_MODEL') or 'llama-3.1-8b-instant'
        try:
            chat_completion = client.chat.completions.create(
                messages=messages,
                model=model_to_use
            )
        except Exception as e:
            if "429" in str(e) and model_to_use != 'llama-3.1-8b-instant':
                print(f"Model {model_to_use} rate limited in chat. Falling back to llama-3.1-8b-instant...")
                model_to_use = 'llama-3.1-8b-instant'
                chat_completion = client.chat.completions.create(
                    messages=messages,
                    model=model_to_use
                )
            else:
                raise e
        
        return jsonify({"response": chat_completion.choices[0].message.content})

    except Exception as e:
        return jsonify({"error": f"Chat failed: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    print(f"Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)