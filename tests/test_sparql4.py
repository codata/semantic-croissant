import urllib.request, urllib.parse, json

query = """
PREFIX schema: <https://schema.org/>
PREFIX schema_http: <http://schema.org/>
PREFIX cr: <http://mlcommons.org/croissant/>

SELECT ?name ?desc ?dataType ?column ?fileObject WHERE {
  ?dataset a schema:Dataset .
  
  {
    ?dataset schema:distribution|schema_http:distribution ?dist .
    ?dist schema:hasPart|schema_http:hasPart|cr:recordSet ?rs .
    ?rs cr:field|cr:hasPart ?field .
  } UNION {
    ?dataset schema:hasPart|schema_http:hasPart|cr:recordSet ?rs .
    ?rs cr:field|cr:hasPart ?field .
  } UNION {
    ?dataset cr:recordSet ?rs .
    ?rs cr:field ?field .
  }
  
  ?field a cr:Field .
  
  ?field schema:name|schema_http:name|cr:name ?name .
  
  OPTIONAL { ?field schema:description|schema_http:description|cr:description ?desc }
  OPTIONAL { ?field cr:dataType ?dataType }
  OPTIONAL { 
    ?field cr:source ?source .
    ?source cr:extract ?extract .
    ?extract cr:column ?column .
  }
  OPTIONAL { 
    ?field cr:source ?source2 .
    ?source2 cr:fileObject ?fileObjNode .
    ?fileObjNode schema:name|schema_http:name|cr:name ?fileObject .
  }
} LIMIT 10
"""
encoded = urllib.parse.urlencode({"query": query})
url = f"http://localhost:7011/?{encoded}"
req = urllib.request.Request(url, headers={"Accept": "application/json"})
try:
    with urllib.request.urlopen(req) as response:
        print(json.dumps(json.loads(response.read().decode()).get("results", {}).get("bindings", []), indent=2))
except Exception as e:
    print("Error:", e)
