import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

url = 'http://127.0.0.1:5001/api/analyze'
payload = {
    'url': 'https://www.vihilinfotech.com',
    'apiKey': os.getenv('GROQ_API_KEY') or 'your_groq_api_key_here'
}
headers = {'Content-Type': 'application/json'}

print("Sending request to /api/analyze for https://www.vihilinfotech.com...")
try:
    resp = requests.post(url, json=payload, headers=headers, timeout=180)
    print('Status:', resp.status_code)
    if resp.status_code == 200:
        data = resp.json()
        print('Response JSON:')
        print(json.dumps(data, indent=2))
    else:
        print('Error Response:', resp.text)
except Exception as e:
    print('Request failed:', e)
