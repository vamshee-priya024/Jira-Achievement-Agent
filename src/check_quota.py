# Quick script to check your Gemini quota and rate limit headers
import os, requests
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

api_key = os.environ.get("GEMINI_API_KEY", "")
if not api_key:
    print("❌ No GEMINI_API_KEY found in .env")
    exit(1)

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

body = {
    "contents": [{"role": "user", "parts": [{"text": "Say hello in one word."}]}],
    "generationConfig": {"maxOutputTokens": 10}
}

print("Sending a minimal test request to Gemini...")
response = requests.post(url, headers={"Content-Type": "application/json"}, json=body)

print(f"\nStatus code : {response.status_code}")
print(f"\nRate limit headers:")
for k, v in response.headers.items():
    if any(x in k.lower() for x in ["limit", "quota", "remain", "retry", "rate"]):
        print(f"  {k}: {v}")

if response.status_code == 200:
    print(f"\n✅ API key works! Response: {response.json()['candidates'][0]['content']['parts'][0]['text']}")
elif response.status_code == 429:
    print(f"\n❌ Still rate limited.")
    print(f"Response body: {response.text}")
else:
    print(f"\nResponse body: {response.text}")