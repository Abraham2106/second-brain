import requests

payload = {
    "model": "gemini-3.1-pro",
    "messages": [
        {"role": "user", "content": "Hello. Talk a lot."}
    ]
}

print("Pinging proxy...")
try:
    r = requests.post("http://127.0.0.1:8000/v1/chat/completions", json=payload, timeout=20)
    print("Status:", r.status_code)
    print("Response:", r.text)
except Exception as e:
    print("Failed:", e)
