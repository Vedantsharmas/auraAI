import re

with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    js_content = f.read()

keywords = [
    "vihil3010", "Kinjal", "Jaydeep", "panchal", "Finnovationz",
    "Indore", "Madhya Pradesh", "ContactUs", "who-we-are", "our-services",
    "how-we-work", "vihilCareer", "address", "phone", "email", "pricing",
    "services", "products", "founder", "CEO", "Tailer Mode", "TermsAndCondition",
    "privacy-policy"
]

def search_windows(kw, count=5):
    print(f"\n=================== SEARCH WINDOWS FOR: '{kw}' ===================")
    matches = [m.start() for m in re.finditer(re.escape(kw), js_content, re.IGNORECASE)]
    print(f"Found {len(matches)} occurrences.")
    seen = set()
    output_count = 0
    for idx in matches:
        if output_count >= count:
            break
        # Get window of 1000 characters
        start = max(0, idx - 400)
        end = min(len(js_content), idx + 600)
        snippet = js_content[start:end]
        # normalize whitespace
        snippet_clean = " ".join(snippet.split())
        # check if too similar to what we've seen
        sig = snippet_clean[:100]
        if sig in seen:
            continue
        seen.add(sig)
        print(f"--- Occurrence at index {idx} ---")
        print(snippet_clean)
        output_count += 1

# Let's search some key terms
search_windows("vihil3010", 3)
search_windows("Kinjal", 3)
search_windows("panchal", 3)
search_windows("Indore", 3)
search_windows("ContactUs", 2)
search_windows("who-we-are", 2)
search_windows("vihilCareer", 2)
search_windows("how-we-work", 2)
