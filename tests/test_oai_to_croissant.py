import requests
import json
import time

OLLAMA_HOST = "http://10.147.18.82:11435"
MODEL_NAME = "gemma4-croissant"
URL = "https://dataverse.nl/api/datasets/export?exporter=OAI_ORE&persistentId=doi%3A10.34894/YAMT7R"

def fetch_oai_ore():
    print(f"Fetching OAI_ORE from {URL}...")
    try:
        response = requests.get(URL, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Failed to fetch OAI_ORE: {e}")
        return None

def test_performance():
    oai_data = fetch_oai_ore()
    if not oai_data:
        return

    print(f"\n--- Testing {MODEL_NAME} ---")
    prompt = f"Convert the following OAI_ORE metadata to Croissant JSON-LD format. Extract datasets, distributions, authors, and variables.\n\nIMPORTANT: For any fields or data in the OAI_ORE that do not have a standard mapping in Croissant, include them in the JSON-LD under a custom field called 'unmappedFields' as a list of key-value pairs.\n\nOAI_ORE Data:\n```json\n{oai_data}\n```"
    
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }
    
    start_time = time.time()
    try:
        response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=600)
        response.raise_for_status()
        end_time = time.time()
        
        data = response.json()
        print("Status: Success")
        print(f"Total Request Time: {end_time - start_time:.2f} s")
        print(f"Prompt Eval Tokens: {data.get('prompt_eval_count')} in {data.get('prompt_eval_duration', 0) / 1e9:.2f} s")
        print(f"Tokens Generated: {data.get('eval_count')} in {data.get('eval_duration', 0) / 1e9:.2f} s")
        if data.get('eval_duration', 0) > 0:
            speed = data.get('eval_count', 0) / (data.get('eval_duration', 0) / 1e9)
            print(f"Generation Speed: {speed:.2f} tokens/sec")
        print("-" * 40)
        
        output = data.get('response', '')
        
        # Optionally save it
        with open("yamt7r_croissant.jsonld", "w", encoding='utf-8') as f:
            f.write(output)
        print("Output saved to yamt7r_croissant.jsonld")
            
    except requests.exceptions.Timeout:
        print(f"Failed to test {MODEL_NAME}: Request timed out after 600s")
    except Exception as e:
        print(f"Failed to test {MODEL_NAME}: {e}")

if __name__ == "__main__":
    test_performance()
