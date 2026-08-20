import httpx
import asyncio
import json

async def run():
    async with httpx.AsyncClient() as client:
        r = await client.get("http://minio:9000/vault/session_UNF-6_9600qBGzW6wdKU3eIg13w_UNF-6_zHq4jfu7t6hM5NC6hnU8g_did_zqmqr5ap_20260815_115558.jsonld")
        if r.status_code == 200:
            print(json.dumps(r.json(), indent=2))
        else:
            print(f"Failed: {r.status_code}")

asyncio.run(run())
