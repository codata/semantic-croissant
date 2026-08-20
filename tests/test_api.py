import asyncio
import httpx
import json

async def main():
    # 1. Fetch raw JSON-LD
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
        raw = hits[0]["_source"].get("_markdown_text")
        parsed = json.loads(raw)
        
        # 2. Post to api endpoint via localhost:7013
        api_res = await client.post("http://localhost:7013/variables/croissant/raw", json={"jsonld": parsed})
        print(json.dumps(api_res.json(), indent=2))

asyncio.run(main())
