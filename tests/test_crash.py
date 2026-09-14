import asyncio
from api.mcp_server import store_in_vault
import json

async def main():
    payload = json.dumps({"test": "data"})
    res = await store_in_vault(payload, "Test content")
    print(res)

asyncio.run(main())
