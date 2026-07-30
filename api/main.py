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

import urllib.parse

def sanitize_jsonld_ids(obj):
    if isinstance(obj, dict):
        if "@id" in obj and isinstance(obj["@id"], str):
            obj["@id"] = urllib.parse.quote(obj["@id"], safe=':/#?=&')
        for k, v in obj.items():
            sanitize_jsonld_ids(v)
    elif isinstance(obj, list):
        for item in obj:
            sanitize_jsonld_ids(item)

@app.post("/add_record")
async def add_record(request: Request, background_tasks: BackgroundTasks, rebuild: bool = False):
    payload = await request.body()
    
    # 1. Convert JSON-LD to NTriples
    try:
        data = json.loads(payload)
        sanitize_jsonld_ids(data)
        
        # Inject cr:Dataset type to differentiate live records
        if "@type" in data:
            if isinstance(data["@type"], list):
                if "cr:Dataset" not in data["@type"] and "http://mlcommons.org/croissant/Dataset" not in data["@type"]:
                    data["@type"].append("http://mlcommons.org/croissant/Dataset")
            elif isinstance(data["@type"], str):
                data["@type"] = [data["@type"], "http://mlcommons.org/croissant/Dataset"]
        else:
            data["@type"] = "http://mlcommons.org/croissant/Dataset"
            
        g = Graph()
        g.parse(data=json.dumps(data), format='json-ld')
        nt_data = g.serialize(format='nt')
    except Exception as e:
        return {"error": f"Failed to parse JSON-LD: {str(e)}"}, 400

    # 2. Append to data.nt for persistence
    try:
        with open(DATA_FILE, "a") as f:
            f.write(nt_data)
            # Add a newline just in case
            if not nt_data.endswith("\n"):
                f.write("\n")
    except Exception as e:
        return {"error": f"Failed to write to {DATA_FILE}: {str(e)}"}, 500

    # 3. Live INSERT DATA to QLever
    try:
        access_token = os.environ.get("QLEVER_SERVER_ACCESS_TOKEN", "croissant_7643543846_Zs6nw7yi3Z9m")
        # Ensure we only send valid triples. Empty payload causes parse error.
        if nt_data.strip():
            insert_query = f"INSERT DATA {{ {nt_data} }}".encode("utf-8")
            req = urllib.request.Request(
                "http://server-croissant-live:7011/", 
                data=insert_query,
                headers={
                    "Content-type": "application/sparql-update",
                    "Authorization": f"Bearer {access_token}"
                }
            )
            with urllib.request.urlopen(req) as response:
                result = response.read().decode()
                print(f"Live insertion result: {result}", flush=True)
    except Exception as e:
        print(f"Failed to inject triples into live QLever instance: {e}", flush=True)
        # Even if live insertion fails, the data is saved in data.nt, so a rebuild would pick it up

    # 4. Trigger offline rebuild in background if requested
    if rebuild:
        background_tasks.add_task(rebuild_index)
        return {"status": "success", "message": "Record added instantly and full index rebuild scheduled."}
    
    return {"status": "success", "message": "Record added and injected instantly."}

@app.post("/rebuild")
async def trigger_rebuild(background_tasks: BackgroundTasks):
    background_tasks.add_task(rebuild_index)
    return {"status": "success", "message": "Index rebuild scheduled."}

import concurrent.futures

def search_datasets(q: str):
    q_lower = q.lower()
    terms = q_lower.split()
    
    dataset_sets = []
    
    for i, t in enumerate(terms):
        if len(t) <= 2:
            continue
        
        query = f"""
        PREFIX schema: <https://schema.org/>
        PREFIX schema_http: <http://schema.org/>
        PREFIX cr: <http://mlcommons.org/croissant/>
        SELECT DISTINCT ?dataset WHERE {{
          {{
            {{ ?dataset a schema:Dataset }} UNION {{ ?dataset a schema_http:Dataset }}
            ?dataset ?p ?val .
            FILTER(?p IN (schema:name, schema_http:name, schema:description, schema_http:description, schema:keywords, schema_http:keywords))
            FILTER(CONTAINS(?val, "{t}"))
          }}
          UNION
          {{
            ?dataset a cr:Dataset .
            ?dataset ?p_live ?val_live .
            FILTER(?p_live IN (schema:name, schema_http:name, schema:description, schema_http:description, schema:keywords, schema_http:keywords))
            FILTER(CONTAINS(LCASE(STR(?val_live)), "{t}"))
          }}
        }} LIMIT 5000
        """
        
        url = "http://server-croissant-live:7011/"
        data = urllib.parse.urlencode({"query": query}).encode('ascii')
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode())
                bindings = res_data.get("results", {}).get("bindings", [])
                dataset_ids = set(b["dataset"]["value"] for b in bindings)
                dataset_sets.append(dataset_ids)
        except Exception as e:
            print(f"Search dataset query failed for term '{t}': {e}")
            return []

    if not dataset_sets:
        return []
        
    final_datasets = list(set.intersection(*dataset_sets))
    return final_datasets

def get_datasets_properties(dataset_ids):
    if not dataset_ids:
        return []
        
    in_values = ", ".join([f'"_:{ds}"' if ds.startswith('bn') else f'"{ds}"' for ds in dataset_ids])
    
    sparql = f"""
    PREFIX schema: <https://schema.org/>
    PREFIX schema_http: <http://schema.org/>
    PREFIX cr: <http://mlcommons.org/croissant/>
    PREFIX sc: <https://schema.org/>
    SELECT DISTINCT ?dataset ?name ?description ?keyword ?url ?creator_name ?citation ?identifier WHERE {{
      {{ ?dataset a schema:Dataset }} UNION {{ ?dataset a schema_http:Dataset }} UNION {{ ?dataset a cr:Dataset }}
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
      OPTIONAL {{
        {{ ?dataset schema:creator ?creator_node }} UNION {{ ?dataset schema_http:creator ?creator_node }}
        {{ ?creator_node schema:name ?creator_name }} UNION {{ ?creator_node schema_http:name ?creator_name }}
      }}
      OPTIONAL {{
        ?dataset cr:citeAs ?citation
      }}
      OPTIONAL {{
        {{ ?dataset schema:identifier ?identifier }} UNION {{ ?dataset schema_http:identifier ?identifier }}
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
                    "creator_name": b.get("creator_name"),
                    "citation": b.get("citation"),
                    "identifier": b.get("identifier"),
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
                if g["creator_name"]: item["creator_name"] = g["creator_name"]
                if g["citation"]: item["citation"] = g["citation"]
                if g["identifier"]: item["identifier"] = g["identifier"]
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

from fastapi.responses import PlainTextResponse

@app.get("/croissant")
def get_croissant_catalog(id: str = None, q: str = None, limit: int = 500, page: int = 1, format: str = "json-ld"):
    if id:
        # User requested a specific dataset ID
        filter_str = f"_:{id}" if id.startswith("bn") else id
        filter_str_alt = filter_str.replace("https://", "http://") if "https://" in filter_str else filter_str.replace("http://", "https://")
        
        base_subquery = f"""
        SELECT ?dataset WHERE {{
          {{ ?dataset a schema:Dataset }} UNION {{ ?dataset a schema_http:Dataset }} UNION {{ ?dataset a cr:Dataset }}
          OPTIONAL {{ ?dataset schema:url|schema_http:url ?u1 }}
          OPTIONAL {{ ?dataset schema:contentUrl|schema_http:contentUrl ?u2 }}
          FILTER(STR(?dataset) = "{filter_str}" || STR(?u1) = "{filter_str}" || STR(?u2) = "{filter_str}" || STR(?dataset) = "{filter_str_alt}" || STR(?u1) = "{filter_str_alt}" || STR(?u2) = "{filter_str_alt}")
        }}
        """
        
        # Level 1
        q1 = f"""
        PREFIX schema: <https://schema.org/>
        PREFIX schema_http: <http://schema.org/>
        PREFIX cr: <http://mlcommons.org/croissant/>
        SELECT ?dataset ?p1 ?o1 WHERE {{
          {{ {base_subquery} }}
          ?dataset ?p1 ?o1 .
        }}
        """
        
        # Level 2
        q2 = f"""
        PREFIX schema: <https://schema.org/>
        PREFIX schema_http: <http://schema.org/>
        PREFIX cr: <http://mlcommons.org/croissant/>
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
        PREFIX cr: <http://mlcommons.org/croissant/>
        SELECT ?dataset ?p1 ?o1 ?p2 ?o2 ?p3 ?o3 WHERE {{
          {{ {base_subquery} }}
          ?dataset ?p1 ?o1 .
          ?o1 ?p2 ?o2 .
          ?o2 ?p3 ?o3 .
        }}
        """
        
        # Level 4
        q4 = f"""
        PREFIX schema: <https://schema.org/>
        PREFIX schema_http: <http://schema.org/>
        PREFIX cr: <http://mlcommons.org/croissant/>
        SELECT ?dataset ?p1 ?o1 ?p2 ?o2 ?p3 ?o3 ?p4 ?o4 WHERE {{
          {{ {base_subquery} }}
          ?dataset ?p1 ?o1 .
          ?o1 ?p2 ?o2 .
          ?o2 ?p3 ?o3 .
          ?o3 ?p4 ?o4 .
        }}
        """
        
        # Level 5
        q5 = f"""
        PREFIX schema: <https://schema.org/>
        PREFIX schema_http: <http://schema.org/>
        PREFIX cr: <http://mlcommons.org/croissant/>
        SELECT ?dataset ?p1 ?o1 ?p2 ?o2 ?p3 ?o3 ?p4 ?o4 ?p5 ?o5 WHERE {{
          {{ {base_subquery} }}
          ?dataset ?p1 ?o1 .
          ?o1 ?p2 ?o2 .
          ?o2 ?p3 ?o3 .
          ?o3 ?p4 ?o4 .
          ?o4 ?p5 ?o5 .
        }}
        """
        
        def run_q(query):
            encoded = urllib.parse.urlencode({"query": query})
            url = f"http://server-croissant-live:7011/?{encoded}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode()).get("results", {}).get("bindings", [])
                
        try:
            print(q1, flush=True)
            b1 = run_q(q1)
            print(f"b1: {b1}", flush=True)
            if not b1:
                return {"error": "Dataset not found"}
                
            b2 = run_q(q2)
            b3 = run_q(q3)
            b4 = run_q(q4)
            b5 = run_q(q5)
            
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
                
            for b in b4:
                o3 = b["o3"]["value"]
                add_prop(o3, b["p4"]["value"], b["o4"]["value"], b["o4"]["type"])
                
            for b in b5:
                o4 = b["o4"]["value"]
                add_prop(o4, b["p5"]["value"], b["o5"]["value"], b["o5"]["type"])
                
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
                PREFIX cr: <http://mlcommons.org/croissant/>
                
                SELECT DISTINCT ?dataset ?name ?description ?keyword ?url ?creator_name ?citation ?identifier
                WHERE {{
                  {{ ?dataset a schema:Dataset . }}
                  UNION
                  {{ ?dataset a schema_http:Dataset . }}
                  UNION
                  {{ ?dataset a cr:Dataset . }}
                  
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
                  OPTIONAL {{
                    {{ ?dataset schema:creator ?creator_node }} UNION {{ ?dataset schema_http:creator ?creator_node }}
                    {{ ?creator_node schema:name ?creator_name }} UNION {{ ?creator_node schema_http:name ?creator_name }}
                  }}
                  OPTIONAL {{
                    ?dataset cr:citeAs ?citation
                  }}
                  OPTIONAL {{
                    {{ ?dataset schema:identifier ?identifier }} UNION {{ ?dataset schema_http:identifier ?identifier }}
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
                    if "creator_name" in b:
                        datasets[ds_id]["schema:creator_name"] = b["creator_name"]["value"]
                    if "citation" in b:
                        datasets[ds_id]["cr:citeAs"] = b["citation"]["value"]
                    if "identifier" in b:
                        datasets[ds_id]["schema:identifier"] = b["identifier"]["value"]
                
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
            
            if format == "markdown":
                md = ["# Search Results\n"]
                for ds in dataset_list:
                    name = ds.get("schema:name", "Unknown Dataset")
                    desc = ds.get("schema:description", "No description provided.")
                    url = ds.get("schema:url", "No URL")
                    ds_id = ds.get("@id", "")
                    
                    # Extract persistent identifier (prefer schema:identifier over url if it looks like a DOI)
                    identifier = ds.get("schema:identifier")
                    if not identifier:
                        identifier = url
                        
                    author = ds.get("schema:creator_name", "Unknown Author")
                    citation = ds.get("cr:citeAs", "No citation provided.")
                    
                    primary_id = identifier if (identifier and identifier != "No URL") else ds_id
                    
                    md.append(f"## {name}")
                    md.append(f"**Dataset ID:** `{primary_id}`")
                    if primary_id != ds_id:
                        md.append(f"*(Internal ID: {ds_id})*")
                    md.append(f"**Author:** {author}")
                    md.append(f"**Description:** {desc}\n")
                    md.append(f"**Citation:**\n```\n{citation}\n```\n")
                return PlainTextResponse("\n".join(md))
                
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



@app.get("/hazard-info")
async def hazard_info(q: str = None):
    """Returns the full HIPs Croissant content with all links and instructions for LLMs. Can filter by HIPs code or description."""
    hips_path = "/app/hips/semantic_croissant.json"
    if not os.path.exists(hips_path):
        raise HTTPException(status_code=404, detail="Hazard Info Profiles not found on server.")
    with open(hips_path, "r") as f:
        data = json.load(f)
        
    if q:
        q_lower = q.lower()
        filtered_datasets = []
        for d in data.get("dataset", []):
            hips_code = d.get("cr:hasPart", {}).get("hipsCode", "").lower()
            name = d.get("name", "").lower()
            desc = d.get("description", "").lower()
            
            if q_lower in hips_code or q_lower in name or q_lower in desc:
                filtered_datasets.append(d)
                
        data["dataset"] = filtered_datasets
        if "cr:recordSet" in data:
            data["cr:recordSet"]["description"] = f"Filtered index of HIPS datasets. Total datasets matching '{q}': {len(filtered_datasets)}."
            
    return data

@app.get("/variables/sparql")
def get_variables_sparql(id: str):
    import urllib.parse
    
    # Unquote in case the LLM sent urlencoded (e.g. doi%3A...)
    id = urllib.parse.unquote(id)
    
    if not id.startswith("bn"):
        # Resolve identifier/URL to a bnode dataset ID first using CONTAINS
        resolve_query = f"""
        SELECT ?dataset WHERE {{
          ?dataset <https://schema.org/identifier>|<http://schema.org/identifier>|<https://schema.org/url>|<http://schema.org/url> ?id .
          FILTER(CONTAINS(STR(?id), "{id}"))
        }} LIMIT 1
        """
        enc_res = urllib.parse.urlencode({"query": resolve_query}).encode("utf-8")
        req_res = urllib.request.Request("http://server-croissant-live:7011/", data=enc_res, headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req_res) as response_res:
                res_bindings = json.loads(response_res.read().decode()).get("results", {}).get("bindings", [])
                if res_bindings and "dataset" in res_bindings[0]:
                    id = res_bindings[0]["dataset"]["value"]
        except:
            pass
            
    filter_str = f"_:{id}" if id.startswith("bn") else id
    filter_str_alt = filter_str.replace("https://", "http://") if "https://" in filter_str else filter_str.replace("http://", "https://")
    
    query = f"""
    PREFIX schema: <https://schema.org/>
    PREFIX schema_http: <http://schema.org/>
    PREFIX cr: <http://mlcommons.org/croissant/>

    SELECT ?dataset ?identifier ?url ?name ?desc ?dataType ?column ?fileObject WHERE {{
      {{
        SELECT ?dataset ?identifier ?url WHERE {{
          {{ ?dataset a schema:Dataset }} UNION {{ ?dataset a schema_http:Dataset }} UNION {{ ?dataset a cr:Dataset }}
          OPTIONAL {{ ?dataset schema:url|schema_http:url ?u1 }}
          OPTIONAL {{ ?dataset schema:contentUrl|schema_http:contentUrl ?u2 }}
          FILTER(STR(?dataset) = "{filter_str}" || STR(?u1) = "{filter_str}" || STR(?u2) = "{filter_str}" || STR(?dataset) = "{filter_str_alt}" || STR(?u1) = "{filter_str_alt}" || STR(?u2) = "{filter_str_alt}")
        }}
        OPTIONAL {{ ?dataset schema:identifier|schema_http:identifier ?identifier }}
        OPTIONAL {{ ?dataset schema:url|schema_http:url ?url }}
      }}
      
      {{
        ?dataset schema:distribution|schema_http:distribution ?dist .
        ?dist schema:hasPart|schema_http:hasPart|cr:recordSet ?rs .
        ?rs cr:field|cr:hasPart ?field .
      }} UNION {{
        ?dataset schema:hasPart|schema_http:hasPart|cr:recordSet ?rs .
        ?rs cr:field|cr:hasPart ?field .
      }} UNION {{
        ?dataset cr:recordSet ?rs .
        ?rs cr:field ?field .
      }}
      
      ?field a cr:Field .
      
      ?field schema:name|schema_http:name|cr:name ?name .
      
      OPTIONAL {{ ?field schema:description|schema_http:description|cr:description ?desc }}
      OPTIONAL {{ ?field cr:dataType ?dataType }}
      OPTIONAL {{ 
        ?field cr:source ?source .
        ?source cr:extract ?extract .
        ?extract cr:column ?column .
      }}
      OPTIONAL {{ 
        ?field cr:source ?source2 .
        ?source2 cr:fileObject ?fileObjNode .
        ?fileObjNode schema:name|schema_http:name|cr:name ?fileObject .
      }}
    }} LIMIT 5000
    """
    
    encoded = urllib.parse.urlencode({"query": query}).encode("utf-8")
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
            bindings = json.loads(response.read().decode()).get("results", {}).get("bindings", [])
            variables = []
            dataset_id = ""
            identifier = ""
            unique_fields = {}
            for b in bindings:
                if not dataset_id and "dataset" in b:
                    dataset_id = b["dataset"]["value"]
                if not identifier:
                    if "identifier" in b:
                        identifier = b["identifier"]["value"]
                    elif "url" in b:
                        identifier = b["url"]["value"]
                    
                name = b.get("name", {}).get("value", "")
                desc = b.get("desc", {}).get("value", "")
                col = b.get("column", {}).get("value", "")
                fileObj = b.get("fileObject", {}).get("value", "")
                
                key = f"{name}|{col}|{fileObj}"
                if name and key not in unique_fields:
                    v = {
                        "name": name,
                        "description": desc
                    }
                    if col: v["column"] = col
                    if fileObj: v["fileObject"] = fileObj
                    unique_fields[key] = v
                    variables.append(v)
            
            return {
                "dataset_id": dataset_id,
                "identifier": identifier,
                "variables": variables
            }
    except Exception as e:
        return {"error": str(e), "variables": []}

@app.get("/variables/croissant")
def get_variables_croissant(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                return {"error": "URL did not return valid JSON. Ensure you are pointing to a JSON-LD file or API endpoint, not an HTML landing page.", "variables": []}
            
        fields = []
        def extract_field_data(f_obj):
            source = f_obj.get("source") or f_obj.get("cr:source") or {}
            extract = source.get("extract") or source.get("cr:extract") or {}
            file_obj = source.get("fileObject") or source.get("cr:fileObject") or {}
            
            return {
                "name": f_obj.get("schema:name") or f_obj.get("name") or extract.get("column") or extract.get("cr:column") or "",
                "description": f_obj.get("schema:description") or f_obj.get("description") or "",
                "column": extract.get("column") or extract.get("cr:column") or "",
                "fileObject": file_obj.get("@id") or ""
            }

        def walk(obj):
            if isinstance(obj, dict):
                t = obj.get("@type", "")
                if t == "cr:Field" or t == "Field" or (isinstance(t, list) and ("cr:Field" in t or "Field" in t)):
                    fields.append(extract_field_data(obj))
                # Check for "field" or "cr:field" arrays containing fields directly
                elif "field" in obj and isinstance(obj["field"], list):
                    for f in obj["field"]:
                        if isinstance(f, dict):
                            fields.append(extract_field_data(f))
                elif "cr:field" in obj and isinstance(obj["cr:field"], list):
                    for f in obj["cr:field"]:
                        if isinstance(f, dict):
                            fields.append(extract_field_data(f))
                for k, v in obj.items():
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)
                    
        walk(data)
        
        # Deduplicate fields by name
        unique_fields = {}
        for f in fields:
            key = f"{f['name']}|{f['column']}|{f['fileObject']}"
            if f["name"] and key not in unique_fields:
                unique_fields[key] = f
                
        return {"variables": list(unique_fields.values())}
    except Exception as e:
        return {"error": str(e), "variables": []}

@app.get("/variables/oai")
def get_variables_oai(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                return {"error": "URL did not return valid JSON. Ensure you are pointing to a JSON-LD file or API endpoint, not an HTML landing page.", "questions": [], "variables": []}
            
        questions = []
        variables = []
        
        def walk(obj):
            if isinstance(obj, dict):
                if "questionInformation:questionName" in obj:
                    questions.append({
                        "name": obj.get("questionInformation:questionName", ""),
                        "text": obj.get("questionInformation:questionText", "")
                    })
                if "variableInformation:variableName" in obj:
                    variables.append({
                        "name": obj.get("variableInformation:variableName", ""),
                        "label": obj.get("variableInformation:variableLabel", "")
                    })
                for k, v in obj.items():
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)
                    
        walk(data)
        
        return {
            "questions": questions,
            "variables": variables
        }
    except Exception as e:
        return {"error": str(e), "questions": [], "variables": []}
