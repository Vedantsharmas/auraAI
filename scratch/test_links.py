import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

url = 'https://www.vihilinfotech.com'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

resp = requests.get(url, headers=headers)
soup = BeautifulSoup(resp.text, 'html.parser')
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
    print(f"Link: {href} -> Resolved: {resolved} -> Domain: {resolved_domain} -> Internal: {is_internal}")
