import re

with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    js = f.read()

# Let's search for "question:" in js.
# We will grab all items in the array containing "question:"
idx = js.find('question:"')
if idx != -1:
    print("\n--- FAQ items chunk ---")
    chunk = js[idx - 500: idx + 4000]
    faq_items = re.findall(r'\{id:\d+,question:"[^"]+",answer:"[^"]+"\}', chunk)
    for f in faq_items:
        print(f)
else:
    print("No double quote question found. Let's try single quotes.")
    idx = js.find("question:'")
    if idx != -1:
        chunk = js[idx - 500: idx + 4000]
        faq_items = re.findall(r"\{id:\d+,question:'[^']+',answer:'[^']+'\}", chunk)
        for f in faq_items:
            print(f)
