import re

with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    js = f.read()

# Let's search for common contact fields.
# We will search for all occurrences of "+91", "phone", "email", "address", "location"

print("\n--- Phone numbers search ---")
# Search for patterns starting with +91 or common indian phone formats
phones = re.findall(r'(?:\+91|91|0)[0-9\-\s]{10,12}', js)
print("Phones:", set(phones[:10]))

# Let's check for any contact details section.
# Often there's a React component ContactUs or similar that has state or rendering.
# Let's print snippets containing "email" or "phone" or "address" that have text.
idx = 0
found_count = 0
while True:
    idx = js.find("ContactUs", idx)
    if idx == -1:
        break
    print(f"\n--- ContactUs Context {found_count} ---")
    print(js[idx-300:idx+700])
    idx += len("ContactUs")
    found_count += 1
    if found_count > 10:
        break
