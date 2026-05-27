import requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5'
}

for url in ['https://example.com', 'https://news.ycombinator.com', 'https://www.vihilinfotech.com']:
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        print(f"URL: {url} -> Status: {resp.status_code}, Length: {len(resp.text)}")
    except Exception as e:
        print(f"URL: {url} -> Failed: {e}")
