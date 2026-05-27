import re

with open("scratch/main_js.js", "r", encoding="utf-8") as f:
    js_content = f.read()

# 1. Emails
emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', js_content)
print("Emails found:", set(emails))

# 2. Phone numbers (look for common patterns)
phones = re.findall(r'\+?[0-9]{2,4}[-\s]?[0-9]{3,5}[-\s]?[0-9]{4,6}', js_content)
# Filter for typical lengths to avoid noise
phones = [p for p in phones if len(re.sub(r'\D', '', p)) >= 10]
print("Phones found:", set(phones[:20]))

# 3. Social media links
social_domains = ['facebook.com', 'twitter.com', 'linkedin.com', 'instagram.com', 'youtube.com', 'github.com']
socials_found = []
for domain in social_domains:
    # search for url-like structures with these domains
    matches = re.findall(r'https?://[a-zA-Z0-9.-]*' + re.escape(domain) + r'/[a-zA-Z0-9./_\-%?&=]*', js_content)
    socials_found.extend(matches)
print("Socials found:", set(socials_found))

# 4. Search for locations/addresses
# Let's search for some patterns
locations = re.findall(r'(?:Indore|India|Address|Office|Street|Road|City|State|Zip|Postal|HQ|Headquarter|Madhya Pradesh)[^a-zA-Z0-9]{1,10}[a-zA-Z0-9\s,.\-]{5,100}', js_content, re.IGNORECASE)
print("\nSome potential addresses/locations found:")
for loc in set(locations[:30]):
    print("-", loc.strip())

# 5. Let's see some text segments that look like service names or titles
# React components/routing
routes = re.findall(r'path:"([^"]+)"', js_content)
routes2 = re.findall(r'path:\'([^\']+)\'', js_content)
print("\nRoutes:", set(routes + routes2))

# Let's find some headers or specific titles
titles = re.findall(r'["\']([A-Z][a-zA-Z\s&]{4,30})["\']', js_content)
print("\nSome potential titles/names (Capitalized):")
# Filter out common javascript keywords
excluded = {'react', 'object', 'string', 'number', 'boolean', 'function', 'undefined', 'null', 'array', 'error', 'warning', 'success', 'loading'}
filtered_titles = [t for t in set(titles) if t.lower() not in excluded and len(t) > 6][:100]
print(", ".join(filtered_titles[:50]))
