import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

url = 'https://www.vihilinfotech.com'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="networkidle", timeout=15000)
    html = page.content()
    browser.close()

soup = BeautifulSoup(html, 'html.parser')
parsed_base = urlparse(url)
base_domain = parsed_base.netloc.replace('www.', '')

print(f"Base Domain: {base_domain}")
discovered = []
for a in soup.find_all('a', href=True):
    href = a['href'].strip()
    resolved = urljoin(url, href)
    parsed_resolved = urlparse(resolved)
    resolved_domain = parsed_resolved.netloc.replace('www.', '')
    
    is_internal = base_domain in resolved_domain or not resolved_domain
    if is_internal:
        path = parsed_resolved.path.lower()
        if any(path.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.pdf', '.zip', '.css', '.js', '.mp4', '.xml']):
            continue
        cleaned_url = resolved.split('#')[0].split('?')[0].rstrip('/')
        if cleaned_url and cleaned_url not in discovered:
            discovered.append(cleaned_url)

print("Discovered internal pages:", len(discovered))
for d in discovered:
    print("-", d)
