import httpx
import asyncio
import json

async def run():
    async with httpx.AsyncClient() as client:
        r = await client.get("http://minio:9000/vault/session_UNF-6_4pDvQXB9zKPgOrpvbjgw_UNF-6_4pDvQXB9zKPgOrpvbjgw_did_zqmqr5ap_20260815_111644.jsonld")
        if r.status_code == 200:
            print(json.dumps(r.json(), indent=2))
        else:
            print(f"Failed: {r.status_code}")

asyncio.run(run())
