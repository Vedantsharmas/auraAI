with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    js = f.read()

# Let's search for "Sky Tatva"
idx = js.find("Sky Tatva")
if idx != -1:
    print("\n--- Sky Tatva Address Context ---")
    print(js[idx-500:idx+1500])

# Let's search for other APIs or URLs
# Staging API is https://api.staging.vihilinfotech.com
import re
apis = re.findall(r'https?://[a-zA-Z0-9.-]*vihilinfotech\.com[a-zA-Z0-9./_\-%?&=]*', js)
print("\nAPIs found:", set(apis))

# Let's search for "mailto:"
mailtos = re.findall(r'mailto:[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', js)
print("\nMailtos found:", set(mailtos))

# Let's search for "tel:"
tels = re.findall(r'tel:[a-zA-Z0-9.\-\s+]+', js)
print("\nTels found:", set(tels[:20]))
