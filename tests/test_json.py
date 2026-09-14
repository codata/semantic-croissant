import requests
payload = {
    "model": "qwen3.5:27b",
    "prompt": "Hello",
    "stream": False
}
res = requests.post("http://10.147.18.82:11435/api/generate", json=payload)
print(res.status_code)
print(res.json())
