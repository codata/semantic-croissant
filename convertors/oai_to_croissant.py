import requests
import json
import time
import argparse
import urllib.parse
import os
from rdflib import Graph

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = "gemma4-croissant"

def fetch_oai_ore(doi):
    # Properly encode the DOI
    encoded_doi = urllib.parse.quote(doi)
    url = f"https://dataverse.nl/api/datasets/export?exporter=OAI_ORE&persistentId={encoded_doi}"
    
    print(f"Fetching OAI_ORE from {url}...")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Failed to fetch OAI_ORE: {e}")
        return None

def convert_to_croissant(doi):
    oai_data = fetch_oai_ore(doi)
    if not oai_data:
        return

    print(f"\n--- Processing {doi} using {MODEL_NAME} ---")
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
        
        # Strip markdown formatting
        if output.startswith("```json"):
            output = output[7:]
        if output.startswith("```"):
            output = output[3:]
        if output.endswith("```"):
            output = output[:-3]
        output = output.strip()
        
        # Validation
        print("\n--- Validation ---")
        try:
            json_data = json.loads(output)
            print("✓ JSON is well-formed")
            
            # Write to temporary file for rdflib
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonld', delete=False) as tf:
                json.dump(json_data, tf)
                temp_name = tf.name
                
            try:
                g = Graph()
                g.parse(temp_name, format="json-ld")
                print(f"✓ Valid JSON-LD: Successfully loaded {len(g)} triples into RDF graph.")
            except Exception as e:
                print(f"✗ Invalid JSON-LD schema or namespaces: {e}")
            finally:
                os.remove(temp_name)
        except json.JSONDecodeError as e:
            print(f"✗ Invalid JSON structure: {e}")

        # Save output using a safe filename based on the DOI
        safe_name = doi.replace(":", "_").replace("/", "_")
        output_filename = f"{safe_name}_croissant.jsonld"
        
        with open(output_filename, "w", encoding='utf-8') as f:
            f.write(output)
        print(f"\nOutput saved to {output_filename}")
            
    except requests.exceptions.Timeout:
        print(f"Failed to process {doi}: Request timed out after 600s")
    except Exception as e:
        print(f"Failed to process {doi}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Dataverse OAI_ORE exports to Croissant JSON-LD.")
    parser.add_argument("doi", help="The DOI of the dataset (e.g. doi:10.34894/YAMT7R)")
    args = parser.parse_args()
    
    convert_to_croissant(args.doi)
