import re

print("Searching for pricing terms in main_js.js...")
with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    js = f.read()

terms = ["price", "pricing", "dollar", "inr", "cost", "rupee", "payment", "subscribe", "package", "plan"]
for term in terms:
    matches = list(re.finditer(re.escape(term), js, re.IGNORECASE))
    if matches:
        print(f"'{term}' found {len(matches)} times.")
        # print first few contexts
        for m in matches[:3]:
            print(f"  Context: {js[m.start()-100 : m.start()+150]}")
    else:
        print(f"'{term}' not found.")
