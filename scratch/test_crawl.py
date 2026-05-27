import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

url = 'http://127.0.0.1:5001/api/analyze'
payload = {
    'url': 'https://example.com',
    'apiKey': os.getenv('GROQ_API_KEY') or 'your_groq_api_key_here'
}
headers = {'Content-Type': 'application/json'}
resp = requests.post(url, json=payload, headers=headers)
print('Status:', resp.status_code)
print('Response:', resp.text)
