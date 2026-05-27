from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

url = 'https://www.vihilinfotech.com'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="networkidle", timeout=15000)
    html = page.content()
    browser.close()

soup = BeautifulSoup(html, 'html.parser')
links = soup.find_all('a')
print("Total <a> tags found:", len(links))
for index, a in enumerate(links):
    print(f"{index}: text={a.get_text().strip()} | href={a.get('href')}")
