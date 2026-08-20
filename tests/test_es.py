import asyncio
import httpx
import json
from api.main import extract_variables_from_croissant_data

async def main():
    dataset_id_or_url = "https://doi.org/10.7910/DVN/PUWWV9"
    async with httpx.AsyncClient(timeout=30.0) as client:
        es_res = await client.post("http://localhost:9200/_search", json={
            "query": {
                "multi_match": {
                    "query": dataset_id_or_url,
                    "fields": ["url", "schema:url", "identifier", "@id"]
                }
            }
        })
        hits = es_res.json().get("hits", {}).get("hits", [])
        if hits:
            raw = hits[0]["_source"].get("_markdown_text")
            data = json.loads(raw)
            res = extract_variables_from_croissant_data(data)
            print(json.dumps(res, indent=2))
        else:
            print("NO HITS")

asyncio.run(main())
