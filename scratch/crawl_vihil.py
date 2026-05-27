import sys
import os
import json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import crawl_and_clean_website

print("Crawling vihilinfotech.com...")
try:
    data = crawl_and_clean_website("https://www.vihilinfotech.com", max_pages=15)
    # save to scratch/vihil_crawled.json
    output_path = os.path.join(os.path.dirname(__file__), 'vihil_crawled.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Success! Saved to:", output_path)
    print("Title:", data.get("title"))
    print("Emails:", data.get("emails"))
    print("CEO:", data.get("ceo"))
    print("Detected Tech:", data.get("detected_tech"))
    print("Crawled Pages:", data.get("crawled_pages"))
except Exception as e:
    import traceback
    traceback.print_exc()
