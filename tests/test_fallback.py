import urllib.request
url = "https://archaeology.datastations.nl/api/datasets/export?exporter=OAI_ORE&persistentId=doi:10.17026/DANS-2CK-VMR4"
req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
with urllib.request.urlopen(req) as response:
    content = response.read().decode()
    print("CONTENT:", content[:100])
