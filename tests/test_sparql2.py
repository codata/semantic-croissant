import urllib.request, urllib.parse, json
query = """
PREFIX schema: <https://schema.org/>
PREFIX schema_http: <http://schema.org/>
PREFIX cr: <http://mlcommons.org/croissant/>

SELECT ?name ?desc ?dataType ?column WHERE {
  ?field a cr:Field .
  ?field schema:name|schema_http:name|cr:name ?name .
  OPTIONAL { ?field schema:description|schema_http:description|cr:description ?desc }
  OPTIONAL { ?field cr:dataType ?dataType }
  OPTIONAL { 
    ?field cr:source ?source .
    ?source cr:extract ?extract .
    ?extract cr:column ?column .
  }
  ?dataset (schema:recordSet|schema_http:recordSet|cr:recordSet|schema:distribution|schema_http:distribution)* / (cr:field|cr:hasPart|schema:hasPart|schema_http:hasPart)* ?field .
  FILTER(STR(?dataset) = "bn36")
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
