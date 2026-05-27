with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    js = f.read()

# We want to find the definition of component KA.
# Let's search for KA = or function KA or var KA. Or maybe just "KA" as a variable declaration in a webpack module.
# Let's find matches of KA in the code.
import re

# Let's search for where KA is defined. Usually it looks like: KA = ... or function KA(...)
# Let's look for "KA=" or "KA = "
matches = [m.start() for m in re.finditer(r'\bKA\s*=\s*', js)]
print("Declarations of KA:", matches)
for m in matches:
    print(js[m:m+1500])
    print("--------------------------------------")

# If that doesn't yield much, let's search for "ContactUs" component content.
# Usually contact form fields, addresses, or phone numbers are near.
# Let's search for "phone" or "address" or "location" in the whole file and see where they are.
# Let's write out some sentences we find in the file.
print("\n--- Let's search for common Indian states or cities in the JS ---")
locations = ["Gujarat", "Maharashtra", "Ahmedabad", "Mumbai", "Pune", "Indore", "Delhi", "Noida", "Bangalore", "Bengaluru", "Chennai", "Kolkata", "Surat", "Rajasthan", "Madhya Pradesh"]
for loc in locations:
    count = js.lower().count(loc.lower())
    if count > 0:
        print(f"{loc}: {count} occurrences")
        # print context
        idx = js.lower().find(loc.lower())
        print(f"Context: {js[idx-100:idx+200]}")
