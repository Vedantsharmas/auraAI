import sys
import os
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

url = "https://www.vihilinfotech.com"
print("Fetching via Requests:")
try:
    r = requests.get(url, timeout=10)
    print("Status:", r.status_code)
    print("Length:", len(r.text))
    soup = BeautifulSoup(r.text, "html.parser")
    print("Text length:", len(soup.get_text()))
    print("Div count:", len(soup.find_all("div")))
    print("Links count:", len(soup.find_all("a")))
    print("HTML Headings:")
    for h in soup.find_all(['h1', 'h2', 'h3', 'h4']):
        print("-", h.name, h.get_text().strip())
except Exception as e:
    print("Requests Error:", e)

print("\nFetching via Playwright:")
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(3000)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        print("Playwright HTML Length:", len(html))
        print("Playwright Text length:", len(soup.get_text()))
        print("Playwright Div count:", len(soup.find_all("div")))
        print("Playwright Links count:", len(soup.find_all("a")))
        print("Playwright Headings:")
        for h in soup.find_all(['h1', 'h2', 'h3', 'h4']):
            print("-", h.name, h.get_text().strip())
        
        # Print first 2000 chars of text
        print("\nPlaywright Text Content Snippet:\n", soup.get_text()[:2000])
        browser.close()
except Exception as e:
    print("Playwright Error:", e)
