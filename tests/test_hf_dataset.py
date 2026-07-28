import requests
import os
import sys
import json

# You can set the API_TOKEN environment variable or replace the string below
API_TOKEN = os.environ.get("API_TOKEN", "YOUR_API_TOKEN_HERE")
headers = {"Authorization": f"Bearer {API_TOKEN}"}

def query(api_url):
    print(f"Querying {api_url}...")
    response = requests.get(api_url, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error {response.status_code}: {response.text}")
        return None

if __name__ == "__main__":
    urls = [
        "https://huggingface.co/api/datasets/ibm/duorc/croissant",
        "https://huggingface.co/api/datasets/google/gemma-4-E2B/croissant"
    ]
    
    if len(sys.argv) > 1:
        # If user provides URL arguments, use those instead
        urls = sys.argv[1:]
        
    for url in urls:
        data = query(url)
        if data:
            print(f"\n--- Data for {url} ---")
            print(json.dumps(data, indent=2)[:500] + "\n... (truncated)\n")
