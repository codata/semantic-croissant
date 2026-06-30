from fastapi import FastAPI, Request, BackgroundTasks
import os
import time
import subprocess
import shutil
import urllib.request
import urllib.parse
import json
from rdflib import Graph
app = FastAPI(title="Semantic Croissant API")

DATA_DIR = "/data"
INDEX_DIR = "/volumes/server"
DATA_FILE = os.path.join(DATA_DIR, "data.nt")
QLEVER_FILE = os.path.join(INDEX_DIR, "Qleverfile")

def generate_qleverfile():
    content = """[data]
NAME = croissant
GET_DATA_CMD = cat data.nt > croissant.nt
INDEX_INPUT_FILES = croissant.nt

[server]
PORT = 7011
ACCESS_TOKEN = croissant_7643543846_Zs6nw7yi3Z9m
HOST_NAME = server-croissant-live

[runtime]
SERVER_CONTAINER = semantic-croissant-server-croissant-live-1
SYSTEM = native
"""
    with open(QLEVER_FILE, "w") as f:
        f.write(content)

def rebuild_index():
    if not os.path.exists(QLEVER_FILE):
        generate_qleverfile()
    
    # Copy data.nt to INDEX_DIR so qlever-index container can see it
    shutil.copy(DATA_FILE, os.path.join(INDEX_DIR, "data.nt"))
    
    print("Starting QLever index rebuild...", flush=True)
    try:
        # 1. Delete existing index files
        for f in os.listdir(INDEX_DIR):
            if f.startswith("croissant."):
                os.remove(os.path.join(INDEX_DIR, f))
        
        # 2. Restart QLever Server
        subprocess.run(
            ["docker", "restart", "semantic-croissant-server-croissant-live-1"],
            check=True
        )
        print("Index rebuild completed and server restarted.", flush=True)
    except Exception as e:
        print(f"Error rebuilding index: {e}", flush=True)

@app.post("/add_record")
async def add_record(request: Request, background_tasks: BackgroundTasks, rebuild: bool = True):
    payload = await request.body()
    
    # 1. Convert JSON-LD to NTriples
    try:
        g = Graph()
        g.parse(data=payload, format='json-ld')
        nt_data = g.serialize(format='nt')
    except Exception as e:
        return {"error": f"Failed to parse JSON-LD: {str(e)}"}, 400

    # 2. Append to data.nt
    try:
        with open(DATA_FILE, "a") as f:
            f.write(nt_data)
            # Add a newline just in case
            if not nt_data.endswith("\n"):
                f.write("\n")
    except Exception as e:
        return {"error": f"Failed to write to {DATA_FILE}: {str(e)}"}, 500

    # 3. Trigger rebuild in background
    if rebuild:
        background_tasks.add_task(rebuild_index)
        return {"status": "success", "message": "Record added and index rebuild scheduled."}
    
    return {"status": "success", "message": "Record added without triggering index rebuild."}

@app.post("/rebuild")
async def trigger_rebuild(background_tasks: BackgroundTasks):
    background_tasks.add_task(rebuild_index)
    return {"status": "success", "message": "Index rebuild scheduled."}

import concurrent.futures

def search_datasets(q: str):
    q_lower = q.lower()
    terms = q_lower.split()
    
    name_filters = " && ".join([f'CONTAINS(LCASE(STR(?name)), "{t}")' for t in terms])
    q1 = f"""
    PREFIX schema: <https://schema.org/>
    PREFIX schema_http: <http://schema.org/>
    SELECT DISTINCT ?dataset ?name WHERE {{
      {{ ?dataset a schema:Dataset }} UNION {{ ?dataset a schema_http:Dataset }}
      {{ ?dataset schema:name ?name }} UNION {{ ?dataset schema_http:name ?name }}
      FILTER ({name_filters})
    }} LIMIT 5000
    """
    
    keyword_filters = " && ".join([f'CONTAINS(LCASE(STR(?keyword)), "{t}")' for t in terms])
    q2 = f"""
    PREFIX schema: <https://schema.org/>
    PREFIX schema_http: <http://schema.org/>
    SELECT DISTINCT ?dataset WHERE {{
      {{ ?dataset a schema:Dataset }} UNION {{ ?dataset a schema_http:Dataset }}
      {{ ?dataset schema:keywords ?keyword }} UNION {{ ?dataset schema_http:keywords ?keyword }}
      FILTER ({keyword_filters})
    }} LIMIT 5000
    """
    
    desc_filters = " && ".join([f'CONTAINS(LCASE(STR(?desc)), "{t}")' for t in terms])
    q3 = f"""
    PREFIX schema: <https://schema.org/>
    PREFIX schema_http: <http://schema.org/>
    SELECT DISTINCT ?dataset WHERE {{
      {{ ?dataset a schema:Dataset }} UNION {{ ?dataset a schema_http:Dataset }}
      {{ ?dataset schema:description ?desc }} UNION {{ ?dataset schema_http:description ?desc }}
      FILTER ({desc_filters})
    }} LIMIT 5000
    """
    
    def run_query(query):
        encoded = urllib.parse.urlencode({"query": query})
        url = f"http://server-croissant-live:7011/?{encoded}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode()).get("results", {}).get("bindings", [])
        except Exception:
            return []
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f1 = executor.submit(run_query, q1)
        f2 = executor.submit(run_query, q2)
        f3 = executor.submit(run_query, q3)
        b1, b2, b3 = f1.result(), f2.result(), f3.result()
        
    scores = {}
    
    for b in b1:
        ds = b["dataset"]["value"]
        name = b["name"]["value"]
        scores.setdefault(ds, 0)
        if name.lower() == q_lower:
            scores[ds] += 100
        else:
            scores[ds] += 50
            
    for b in b2:
        ds = b["dataset"]["value"]
        scores.setdefault(ds, 0)
        scores[ds] += 25
        
    for b in b3:
        ds = b["dataset"]["value"]
        scores.setdefault(ds, 0)
        scores[ds] += 10
        
    sorted_datasets = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    return sorted_datasets

def get_datasets_properties(dataset_ids):
    if not dataset_ids:
        return []
        
    in_values = ", ".join([f'"_:{ds}"' if ds.startswith('bn') else f'"{ds}"' for ds in dataset_ids])
    
    sparql = f"""
    PREFIX schema: <https://schema.org/>
    PREFIX schema_http: <http://schema.org/>
    SELECT DISTINCT ?dataset ?name ?description ?keyword ?url WHERE {{
      {{ ?dataset a schema:Dataset }} UNION {{ ?dataset a schema_http:Dataset }}
      FILTER(STR(?dataset) IN ({in_values}))
      
      OPTIONAL {{
        {{ ?dataset schema:name ?name }} UNION {{ ?dataset schema_http:name ?name }}
      }}
      OPTIONAL {{
        {{ ?dataset schema:description ?description }} UNION {{ ?dataset schema_http:description ?description }}
      }}
      OPTIONAL {{
        {{ ?dataset schema:keywords ?keyword }} UNION {{ ?dataset schema_http:keywords ?keyword }}
      }}
      OPTIONAL {{
        {{ ?dataset schema:url ?url }} UNION {{ ?dataset schema_http:url ?url }}
      }}
    }}
    """
    
    encoded = urllib.parse.urlencode({"query": sparql}).encode("utf-8")
    url = "http://server-croissant-live:7011/"
    req = urllib.request.Request(
        url, 
        data=encoded,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode()).get("results", {}).get("bindings", [])
    except Exception:
        return []

@app.get("/search")
def search_keyword(q: str, limit: int = 100, page: int = 1):
    try:
        sorted_datasets = search_datasets(q)
        offset = (page - 1) * limit
        page_datasets = sorted_datasets[offset:offset+limit]
        
        bindings = get_datasets_properties(page_datasets)
        
        # Sort bindings based on page_datasets order
        order_map = {ds: i for i, ds in enumerate(page_datasets)}
        
        # Format similar to raw SPARQL response but grouped and ordered
        results = []
        grouped = {}
        for b in bindings:
            ds = b["dataset"]["value"]
            if ds not in grouped:
                grouped[ds] = {
                    "dataset": b["dataset"],
                    "name": b.get("name"),
                    "description": b.get("description"),
                    "url": b.get("url"),
                    "keywords": set()
                }
            if "keyword" in b:
                grouped[ds]["keywords"].add(b["keyword"]["value"])
        
        for ds in page_datasets:
            if ds in grouped:
                g = grouped[ds]
                item = {
                    "dataset": g["dataset"],
                }
                if g["name"]: item["name"] = g["name"]
                if g["description"]: item["description"] = g["description"]
                if g["url"]: item["url"] = g["url"]
                if g["keywords"]: 
                    item["keyword"] = {"type": "literal", "value": list(g["keywords"])[0]} # Search returns first keyword
                results.append(item)
                
        return {
            "status": "success",
            "page": page,
            "limit": limit,
            "data": results
        }
    except Exception as e:
        return {"error": f"Failed to perform search: {str(e)}"}, 500

@app.get("/croissant")
def get_croissant_catalog(id: str = None, q: str = None, limit: int = 500, page: int = 1):
    if id:
        # User requested a specific dataset ID
        filter_str = f"_:{id}" if id.startswith("bn") else id
        
        # We will build the full graph of the dataset by running 3 levels of depth queries
        base_subquery = f"""
        SELECT ?dataset WHERE {{
          {{ ?dataset a schema:Dataset }} UNION {{ ?dataset a schema_http:Dataset }}
          FILTER(STR(?dataset) = "{filter_str}")
        }}
        """
        
        # Level 1
        q1 = f"""
        PREFIX schema: <https://schema.org/>
        PREFIX schema_http: <http://schema.org/>
        SELECT ?dataset ?p1 ?o1 WHERE {{
          {{ {base_subquery} }}
          ?dataset ?p1 ?o1 .
        }}
        """
        
        # Level 2
        q2 = f"""
        PREFIX schema: <https://schema.org/>
        PREFIX schema_http: <http://schema.org/>
        SELECT ?dataset ?p1 ?o1 ?p2 ?o2 WHERE {{
          {{ {base_subquery} }}
          ?dataset ?p1 ?o1 .
          ?o1 ?p2 ?o2 .
        }}
        """
        
        # Level 3
        q3 = f"""
        PREFIX schema: <https://schema.org/>
        PREFIX schema_http: <http://schema.org/>
        SELECT ?dataset ?p1 ?o1 ?p2 ?o2 ?p3 ?o3 WHERE {{
          {{ {base_subquery} }}
          ?dataset ?p1 ?o1 .
          ?o1 ?p2 ?o2 .
          ?o2 ?p3 ?o3 .
        }}
        """
        
        def run_q(query):
            encoded = urllib.parse.urlencode({"query": query})
            url = f"http://server-croissant-live:7011/?{encoded}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode()).get("results", {}).get("bindings", [])
                
        try:
            b1 = run_q(q1)
            if not b1:
                return {"error": "Dataset not found"}
                
            b2 = run_q(q2)
            b3 = run_q(q3)
            
            # Reconstruct the JSON-LD tree
            nodes = {}
            
            def add_prop(subj, p, obj_val, obj_type):
                if subj not in nodes:
                    nodes[subj] = {}
                # QLever returns full URIs for predicates
                prop = p.replace("https://schema.org/", "schema:").replace("http://schema.org/", "schema:")
                prop = prop.replace("http://mlcommons.org/croissant/", "cr:")
                prop = prop.replace("http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "@type")
                
                if obj_type == "uri":
                    obj = obj_val.replace("https://schema.org/", "schema:").replace("http://schema.org/", "schema:")
                elif obj_type == "bnode":
                    obj = {"@id": obj_val}
                else:
                    obj = obj_val
                    
                if prop not in nodes[subj]:
                    nodes[subj][prop] = []
                
                # Check if obj is already in list (for uniqueness)
                if obj not in nodes[subj][prop]:
                    nodes[subj][prop].append(obj)

            # Process bindings
            for b in b1:
                ds = b["dataset"]["value"]
                add_prop(ds, b["p1"]["value"], b["o1"]["value"], b["o1"]["type"])
                
            for b in b2:
                o1 = b["o1"]["value"]
                add_prop(o1, b["p2"]["value"], b["o2"]["value"], b["o2"]["type"])
                
            for b in b3:
                o2 = b["o2"]["value"]
                add_prop(o2, b["p3"]["value"], b["o3"]["value"], b["o3"]["type"])
                
            # Expand nested nodes
            def expand(node_id):
                if node_id not in nodes:
                    return {"@id": node_id}
                expanded = {}
                for k, vlist in nodes[node_id].items():
                    expanded_vlist = []
                    for v in vlist:
                        if isinstance(v, dict) and "@id" in v:
                            if v["@id"] in nodes:
                                expanded_vlist.append(expand(v["@id"]))
                            else:
                                expanded_vlist.append(v)
                        else:
                            expanded_vlist.append(v)
                    # Flatten single element lists except for specific properties that require lists
                    if len(expanded_vlist) == 1 and k != "schema:dataset":
                        expanded[k] = expanded_vlist[0]
                    else:
                        expanded[k] = expanded_vlist
                # Make sure @id is preserved
                if not node_id.startswith("bn"):
                    expanded["@id"] = node_id
                return expanded
                
            root_id = b1[0]["dataset"]["value"]
            full_record = expand(root_id)
            full_record["@context"] = {
                "schema": "https://schema.org/",
                "cr": "http://mlcommons.org/croissant/"
            }
            return full_record

        except Exception as e:
            return {"error": f"Failed to fetch full record: {str(e)}"}

    else:
        # Catalog logic with optional search ranking
        try:
            if q:
                sorted_datasets = search_datasets(q)
                offset = (page - 1) * limit
                page_datasets = sorted_datasets[offset:offset+limit]
                bindings = get_datasets_properties(page_datasets)
            else:
                offset = (page - 1) * limit
                sparql = f"""
                PREFIX schema: <https://schema.org/>
                PREFIX schema_http: <http://schema.org/>
                
                SELECT DISTINCT ?dataset ?name ?description ?keyword
                WHERE {{
                  {{ ?dataset a schema:Dataset . }}
                  UNION
                  {{ ?dataset a schema_http:Dataset . }}
                  
                  OPTIONAL {{
                    {{ ?dataset schema:name ?name }} UNION {{ ?dataset schema_http:name ?name }}
                  }}
                  OPTIONAL {{
                    {{ ?dataset schema:description ?description }} UNION {{ ?dataset schema_http:description ?description }}
                  }}
                  OPTIONAL {{
                    {{ ?dataset schema:keywords ?keyword }} UNION {{ ?dataset schema_http:keywords ?keyword }}
                  }}
                  OPTIONAL {{
                    {{ ?dataset schema:url ?url }} UNION {{ ?dataset schema_http:url ?url }}
                  }}
                }}
                ORDER BY ?dataset
                LIMIT {limit}
                OFFSET {offset}
                """
                encoded_query = urllib.parse.urlencode({"query": sparql}).encode("utf-8")
                url = "http://server-croissant-live:7011/"
                req = urllib.request.Request(
                    url, 
                    data=encoded_query,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded"
                    }
                )
                with urllib.request.urlopen(req) as response:
                    data = json.loads(response.read().decode())
                    bindings = data.get("results", {}).get("bindings", [])
                    page_datasets = [] # Not used for ordering when q is None
                    
            datasets = {}
            for b in bindings:
                ds_id = b.get("dataset", {}).get("value", "")
                if not ds_id: continue
                
                if ds_id not in datasets:
                    datasets[ds_id] = {
                        "@type": "schema:Dataset",
                        "@id": ds_id,
                        "schema:name": b.get("name", {}).get("value", ""),
                        "schema:description": b.get("description", {}).get("value", ""),
                        "schema:keywords": []
                    }
                    if "url" in b:
                        datasets[ds_id]["schema:url"] = b["url"]["value"]
                
                keyword = b.get("keyword", {}).get("value", "")
                if keyword and keyword not in datasets[ds_id]["schema:keywords"]:
                    datasets[ds_id]["schema:keywords"].append(keyword)
            
            # Sort datasets according to page_datasets if q is provided
            if q:
                dataset_list = []
                for ds in page_datasets:
                    if ds in datasets:
                        dataset_list.append(datasets[ds])
            else:
                dataset_list = list(datasets.values())
            
            croissant_export = {
                "@context": {
                    "schema": "https://schema.org/",
                    "cr": "http://mlcommons.org/croissant/"
                },
                "@type": "schema:DataCatalog",
                "schema:name": "Semantic Croissant Catalog",
                "schema:description": f"A catalog of datasets indexed in the system (Page {page}).",
                "schema:dataset": dataset_list
            }
            
            return croissant_export
            
        except Exception as e:
            return {"error": f"Failed to query QLever: {str(e)}"}, 500


@app.get("/health")
def health():
    return {"status": "ok"}


