import re

with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    js_content = f.read()

# Let's search for some paragraphs or text blocks that look like description text.
# We will search for keywords and extract a larger chunk around them.

def extract_around(keyword, length=1200):
    idx = js_content.find(keyword)
    if idx == -1:
        print(f"Keyword '{keyword}' not found.")
        return
    start = max(0, idx - 100)
    end = min(len(js_content), idx + length)
    print(f"\n--- Snippet for '{keyword}' ---")
    snippet = js_content[start:end]
    # Clean up whitespace and react code a bit for readability
    snippet = re.sub(r'\s+', ' ', snippet)
    print(snippet)

extract_around("who-we-are")
extract_around("our-services")
extract_around("how-we-work")
extract_around("FAQ")
extract_around("ContactUs")
extract_around("vihilCareer")
extract_around("TermsAndCondition")
extract_around("privacy-policy")
extract_around("Jaydeep")
extract_around("Kinjal")
