import requests
import re
import os

url_js = "https://www.vihilinfotech.com/static/js/main.d7698b81.js"
url_css = "https://www.vihilinfotech.com/static/css/main.dba109da.css"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

print("Fetching JS bundle...")
js_resp = requests.get(url_js, headers=headers, timeout=15)
if js_resp.status_code == 200:
    js_path = "scratch/main_js.js"
    with open(js_path, "w", encoding="utf-8") as f:
        f.write(js_resp.text)
    print("JS size:", len(js_resp.text))
else:
    print("JS fetch failed:", js_resp.status_code)

print("Fetching CSS bundle...")
css_resp = requests.get(url_css, headers=headers, timeout=15)
if css_resp.status_code == 200:
    css_path = "scratch/main_css.css"
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(css_resp.text)
    print("CSS size:", len(css_resp.text))
else:
    print("CSS fetch failed:", css_resp.status_code)
