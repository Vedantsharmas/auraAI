with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    js = f.read()

# Let's search for team member definitions.
# We know they look like: {id:..., img:..., desc:..., position:..., name:...}
# Let's search for "position" and "name" near each other.

import re
matches = re.findall(r'\{id:\d+,img:[^}]+,desc:"[^"]+",position:"[^"]+",name:"[^"]+"\}', js)
print("Matches found (double quotes):", len(matches))
for m in matches:
    print(m)

matches_single = re.findall(r"\{id:\d+,img:[^}]+,desc:'[^']+',position:'[^']+',name:'[^']+'\}", js)
print("Matches found (single quotes):", len(matches_single))
for m in matches_single:
    print(m)

# Since they might be formatted slightly differently, let's just grab a chunk of 4000 characters starting from the first "Kinjal patel"
idx = js.find("Kinjal patel")
if idx != -1:
    print("\n--- Team definitions chunk ---")
    chunk = js[idx - 2500: idx + 1500]
    # format a bit
    print(" ".join(chunk.split()))
