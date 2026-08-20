import urllib.request
import json
url = "https://archaeology.datastations.nl/api/datasets/export?exporter=croissant&persistentId=doi:10.17026/DANS-2CK-VMR4"

data = None
try:
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
    with urllib.request.urlopen(req) as response:
        content = response.read().decode()
        print("CONTENT LEN:", len(content))
        data = json.loads(content)
except Exception as e:
    print(f"Exception triggered: {e}")
    if "exporter=croissant" in url:
        fallback_url = url.replace("exporter=croissant", "exporter=OAI_ORE")
        try:
            req_fb = urllib.request.Request(fallback_url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req_fb) as response_fb:
                oai_data = json.loads(response_fb.read().decode())
                print("OAI Data successfully loaded, keys:", oai_data.keys())
            data = {"dummy": "croissant"}
        except Exception as fb_e:
            print(f"Fallback error: {fb_e}")

print("DATA IS:", data)
