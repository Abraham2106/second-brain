import requests

try:
    print("Fetching proxy state...")
    r = requests.get("http://127.0.0.1:8000/proxy-state", timeout=5)
    print("State:", r.json())
except Exception as e:
    print("Error:", e)

payload = {
    "model": "gemini-3.1-pro",
    "messages": [
        {"role": "user", "content": "Hello. Quick response. Who are you?"}
    ]
}

print("Pinging proxy for chat...")
try:
    r = requests.post("http://127.0.0.1:8000/v1/chat/completions", json=payload, timeout=20)
    print("Status:", r.status_code)
    print("Response:", r.text)
except Exception as e:
    print("Chat failed:", e)

try:
    print("Fetching proxy state again...")
    r = requests.get("http://127.0.0.1:8000/proxy-state", timeout=5)
    print("State:", r.json())
except Exception as e:
    print("Error:", e)
