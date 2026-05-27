import re

with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    js = f.read()

# Search for FAQ questions and answers
# FAQ items usually have properties like question, answer or q, a
print("\n--- FAQ search ---")
faq_matches = re.findall(r'(?:question|answer|Q:|A:|title|desc):"[^"]{20,200}"', js)
for m in set(faq_matches[:20]):
    print(m)

# Find office location / address
print("\n--- Address search ---")
# Let's search for things like "office", "street", "road", "city", "country", "india" in case insensitive manner
idx = 0
while True:
    idx = js.find("address", idx)
    if idx == -1:
        break
    print("Address Context:", js[idx-200:idx+300])
    idx += len("address")
    if idx > 2000000: # safety limit
        break

# Let's search for "Indore" specifically, or other cities
idx = 0
while True:
    idx = js.find("Indore", idx)
    if idx == -1:
        break
    print("Indore Context:", js[idx-200:idx+300])
    idx += len("Indore")
    if idx > 2000000:
        break
