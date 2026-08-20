import asyncio
from mcp.client.sse import sse_client
from mcp import ClientSession
import sys

async def main():
    async with sse_client("http://localhost:7070/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Initialized")
            result = await session.call_tool("get_croissant_dataset", {"id": "10.7910/DVN/3VPRGG"})
            print(f"Result: {result}")

asyncio.run(main())
