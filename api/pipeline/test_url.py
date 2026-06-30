import os
import sys
import json
import requests

def check_qlever():
    url = "http://localhost:7011/"
    query = """
    SELECT * WHERE {
      ?s ?p "https://doi.org/10.7910/DVN/2IGG4Z"@en
    } LIMIT 10
    """
    
    try:
        response = requests.post(url, data={"query": query}, headers={"Accept": "application/sparql-results+json"})
        response.raise_for_status()
        bindings = response.json().get("results", {}).get("bindings", [])
        return len(bindings) > 0, bindings
    except Exception as e:
        print(f"QLever error: {e}")
        return False, []

def check_json_folder():
    folder = "/mediaquantum/qlever/croissant"
    for filename in os.listdir(folder):
        if not filename.endswith(".json"): continue
        with open(os.path.join(folder, filename), "r") as f:
            content = f.read()
            if "https://doi.org/10.7910/DVN/2IGG4Z" in content:
                return True, filename
    return False, None

if __name__ == "__main__":
    found_in_json, filename = check_json_folder()
    print(f"Found in JSON raw files: {found_in_json} (File: {filename})")
    
    found_in_qlever, bindings = check_qlever()
    print(f"Found in QLever live server: {found_in_qlever}")
    
    if found_in_qlever:
        print("Test PASSED: URL exists in the SPARQL endpoint!")
        sys.exit(0)
    else:
        print("Test FAILED: URL was not found in the SPARQL endpoint (though it may exist in raw files).")
        sys.exit(1)
