import urllib.request, urllib.parse, json
query = """
PREFIX schema: <https://schema.org/>
PREFIX cr: <http://mlcommons.org/croissant/>

SELECT ?name ?desc ?dataType ?fileObjId ?column WHERE {
  ?field a cr:Field .
  ?field schema:name ?name .
  OPTIONAL { ?field schema:description ?desc }
  OPTIONAL { ?field cr:dataType ?dataType }
  OPTIONAL { 
    ?field cr:source ?source .
    ?source cr:fileObject ?fileObj .
    ?source cr:extract ?extract .
    ?extract cr:column ?column .
  }
} LIMIT 10
"""
encoded = urllib.parse.urlencode({"query": query})
url = f"http://localhost:7011/?{encoded}"
req = urllib.request.Request(url, headers={"Accept": "application/json"})
try:
    with urllib.request.urlopen(req) as response:
        print(json.loads(response.read().decode()).get("results", {}).get("bindings", []))
except Exception as e:
    print("Error:", e)
