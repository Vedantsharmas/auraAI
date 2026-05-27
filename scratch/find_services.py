with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    js = f.read()

# Let's search for "title:" and "desc1:" near each other.
# We saw {id:6,title:"6. Chatbot Development",desc1:...
# Let's search for "1." up to "6." in titles.

import re
matches = re.findall(r'title:"[^"]+",desc1:"[^"]+"', js)
print("Matches found (double quotes):", len(matches))
for m in matches:
    print(m[:300])

# Let's grab the chunk of 6000 characters before the team definitions chunk, which is near "servicesImg"
idx = js.find("6. Chatbot Development")
if idx != -1:
    print("\n--- Services definitions chunk ---")
    chunk = js[idx - 5000: idx + 1000]
    # find all services
    service_matches = re.findall(r'\{id:\d+,title:"[^"]+",desc1:"[^"]+"[^}]*\}', chunk)
    for sm in service_matches:
        print("\nSERVICE:", sm[:500])
