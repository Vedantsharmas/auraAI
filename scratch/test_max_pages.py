import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

url = 'http://127.0.0.1:5001/api/analyze'

payload = {
    'url': 'https://react.dev',
    'apiKey': os.getenv('GROQ_API_KEY') or 'your_groq_api_key_here',
    'maxPages': 5
}
headers = {'Content-Type': 'application/json'}

print("Sending request to /api/analyze with maxPages=5 and url=https://react.dev...")
try:
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    print('Status:', resp.status_code)
    data = resp.json()
    if resp.status_code == 200:
        print('Crawled pages count:', len(data.get('crawled_pages', [])))
        print('Crawled pages:', data.get('crawled_pages'))
    else:
        print('Error response:', data)
except Exception as e:
    print('Request failed:', e)
