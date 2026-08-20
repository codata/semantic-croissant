import json
import requests
import os

def test_upload():
    filepath = "data/openml/openml_31_croissant.jsonld"
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    url = data.get("url", "https://www.openml.org/d/31")
    es_doc = {
        "url": url,
        "expert": "expert/openml",
        "croissant": data,
        "markdown": ""
    }
    
    es_url = "http://localhost:9200"
    index_name = "expert_openml"
    doc_id = url.replace("https://", "").replace("http://", "").replace("/", "_")
    
    print(f"Uploading to {es_url}/{index_name}/_doc/{doc_id}")
    resp = requests.put(f"{es_url}/{index_name}/_doc/{doc_id}", json=es_doc)
    if resp.status_code in (200, 201):
        print(f"Success! {resp.status_code}")
    else:
        print(f"Failed: {resp.status_code} - {resp.text[:500]}")

if __name__ == "__main__":
    test_upload()
