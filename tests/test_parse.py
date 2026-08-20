import json
import urllib.request
from api.main import extract_variables_from_croissant_data

url = "https://dataverse.harvard.edu/api/datasets/export?exporter=croissant&persistentId=doi:10.7910/DVN/PUWWV9"
req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())
    
res = extract_variables_from_croissant_data(data)
print(json.dumps(res, indent=2))
