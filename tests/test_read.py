import httpx
import asyncio

async def run():
    async with httpx.AsyncClient() as client:
        r = await client.get("http://minio:9000/vault/croissant_creators_sdmx_context_UNF-6_uR4EUdVKEyqYxggF0z7bA_did_zqmqr5ap_20260815_104913")
        print(r.status_code)
        
        r2 = await client.get("http://minio:9000/vault/croissant_creators_sdmx_context_UNF-6_uR4EUdVKEyqYxggF0z7bA_did_zqmqr5ap_20260815_104913.md")
        print(r2.status_code)

asyncio.run(run())
