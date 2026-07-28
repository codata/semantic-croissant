import requests
import json
import time

OLLAMA_HOST = "http://10.147.18.82:11435"

def test_performance(model_name, prompt):
    print(f"--- Testing {model_name} ---")
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False
    }
    
    start_time = time.time()
    try:
        response = requests.post(url, json=payload, timeout=180)
        response.raise_for_status()
        data = response.json()
        end_time = time.time()
        
        total_time = end_time - start_time
        
        # Ollama returns metrics in nanoseconds
        eval_count = data.get('eval_count', 0)
        eval_duration_ns = data.get('eval_duration', 0)
        eval_duration_s = eval_duration_ns / 1e9
        
        prompt_eval_count = data.get('prompt_eval_count', 0)
        prompt_eval_duration_ns = data.get('prompt_eval_duration', 0)
        prompt_eval_duration_s = prompt_eval_duration_ns / 1e9
        
        tps = eval_count / eval_duration_s if eval_duration_s > 0 else 0
        
        print(f"Status: Success")
        print(f"Total Request Time: {total_time:.2f} s")
        print(f"Prompt Eval Tokens: {prompt_eval_count} in {prompt_eval_duration_s:.2f} s")
        print(f"Tokens Generated: {eval_count} in {eval_duration_s:.2f} s")
        print(f"Generation Speed: {tps:.2f} tokens/sec")
        print("-" * 40 + "\n")
        
    except Exception as e:
        print(f"Failed to test {model_name}: {e}\n")

if __name__ == "__main__":
    print(f"Testing Ollama Performance on {OLLAMA_HOST}...\n")
    
    croissant_prompt = "Generate Croissant metadata for a tabular dataset called 'Housing Prices' containing 'train.csv' and 'test.csv'. Include name, description, and distribution."
    odrl_prompt = "Evaluate this scenario: An ODRL policy grants 'read' permission. Is the assignee allowed to 'distribute' the asset? Reply with YES or NO and explain based on formal semantics."
    
    test_performance("gemma4-croissant", croissant_prompt)
    # test_performance("gemma4-odrl", odrl_prompt)
