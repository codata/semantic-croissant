import requests
import json
import os
import subprocess
import argparse
import xml.etree.ElementTree as ET
import concurrent.futures
import time
import random

def fetch_hf_model(model_id, token, max_retries=5):
    url = f"https://huggingface.co/api/models/{model_id}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    
    for attempt in range(max_retries):
        print(f"Fetching {url}...")
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            # Rate limit hit
            retry_after = int(response.headers.get("Retry-After", 60))
            # Add jitter to prevent all threads from waking up at the exact same millisecond
            sleep_time = retry_after + random.uniform(1, 10)
            print(f"Rate limited (429) for {model_id}. Sleeping for {sleep_time:.1f}s before retry {attempt+1}/{max_retries}...")
            time.sleep(sleep_time)
        else:
            print(f"Failed to fetch {model_id}: {response.status_code} {response.text}")
            return None
            
    print(f"Failed to fetch {model_id} after {max_retries} retries.")
    return None

def convert_to_intermediate_metadata(model_data):
    """
    Maps Hugging Face Model API JSON to the intermediate metadata format
    expected by the croissant-toolkit 'croissant_expert' skill.
    """
    model_id = model_data.get("id", "unknown/model")
    author = model_data.get("author", "unknown")
    
    metadata = {
        "name": model_id,
        "description": f"Hugging Face Model: {model_id}. Pipeline: {model_data.get('pipeline_tag', 'N/A')}",
        "url": f"https://huggingface.co/{model_id}",
        "creator": author,
        "datePublished": model_data.get("createdAt"),
        "version": model_data.get("sha"),
        "keywords": model_data.get("tags", []),
        "distribution": []
    }

    # Extract license from tags or cardData if possible
    license_tag = next((tag for tag in metadata["keywords"] if tag.startswith("license:")), None)
    if license_tag:
        metadata["license"] = license_tag.split(":", 1)[1]
    elif model_data.get("cardData", {}).get("license"):
        metadata["license"] = model_data.get("cardData", {}).get("license")

    # Map the "siblings" (files in the repo) to distribution objects
    siblings = model_data.get("siblings", [])
    for sib in siblings:
        filename = sib.get("rfilename")
        if not filename:
            continue
            
        mime = "text/plain"
        if filename.endswith(".json"): mime = "application/json"
        elif filename.endswith(".md"): mime = "text/markdown"
        elif filename.endswith(".safetensors") or filename.endswith(".bin"): mime = "application/octet-stream"
            
        metadata["distribution"].append({
            "type": "FileObject",
            "name": filename,
            "contentUrl": f"https://huggingface.co/{model_id}/resolve/main/{filename}",
            "encodingFormat": mime
        })
        
    return metadata

def process_model(model_id, token):
    model_json = fetch_hf_model(model_id, token)
    if not model_json:
        return
        
    safe_id = model_id.replace('/', '_')
    
    # Save original JSON to cache
    os.makedirs("./data/cache", exist_ok=True)
    cache_file = f"./data/cache/{safe_id}.json"
    with open(cache_file, "w") as f:
        json.dump(model_json, f, indent=2)
        
    # Create intermediate metadata
    intermediate = convert_to_intermediate_metadata(model_json)
    intermediate_file = f"./data/cache/{safe_id}_temp.json"
    with open(intermediate_file, "w") as f:
        json.dump(intermediate, f, indent=2)
        
    # Serialize using croissant-toolkit
    os.makedirs("./data/hf", exist_ok=True)
    toolkit_script = "croissant-toolkit/.gemini/skills/croissant_expert/scripts/serialize.py"
    output_file = f"./data/hf/{safe_id}_croissant.jsonld"
    
    # We use capture_output=True to prevent terminal spam when processing many models
    subprocess.run(["python3", toolkit_script, intermediate_file, output_file], capture_output=True)
    
    if os.path.exists(intermediate_file):
        os.remove(intermediate_file)
        
    print(f"Finished processing {model_id} -> {output_file}")

def fetch_sitemap_models(sitemap_url):
    print(f"Fetching sitemap {sitemap_url}...")
    response = requests.get(sitemap_url)
    if response.status_code != 200:
        print(f"Failed to fetch sitemap: {response.status_code}")
        return []
        
    root = ET.fromstring(response.content)
    namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    urls = root.findall('ns:url/ns:loc', namespace)
    
    if not urls:
        urls = root.findall('.//loc')
        
    model_ids = []
    for loc in urls:
        url = loc.text
        if url.startswith("https://huggingface.co/"):
            model_id = url[len("https://huggingface.co/"):]
            model_ids.append(model_id)
            
    return model_ids

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Hugging Face models to Croissant metadata")
    parser.add_argument("model_id", nargs="?", default="google/gemma-4-E2B", help="A single model ID to process (ignored if --sitemap is used)")
    parser.add_argument("--sitemap", type=str, help="URL to a sitemap XML containing model links")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of models to process from the sitemap (0 for all)")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent background workers")
    
    args = parser.parse_args()
    API_TOKEN = os.environ.get("API_TOKEN", "")
    
    if args.sitemap:
        model_ids = fetch_sitemap_models(args.sitemap)
        print(f"Found {len(model_ids)} models in sitemap.")
        
        if args.limit and args.limit > 0:
            model_ids = model_ids[:args.limit]
            print(f"Limiting to first {args.limit} models.")
            
        print(f"Processing models using {args.workers} workers...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(process_model, m_id, API_TOKEN) for m_id in model_ids]
            concurrent.futures.wait(futures)
            
    else:
        process_model(args.model_id, API_TOKEN)

    print("\nAll done!")
