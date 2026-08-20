import asyncio
from mcp.client.sse import sse_client
from mcp import ClientSession
import sys

async def main():
    async with sse_client("http://localhost:7070/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Initialized")
            result = await session.call_tool("extract_variables_from_croissant", {"dataset_id_or_url": "https://doi.org/10.7910/DVN/PUWWV9"})
            print(f"Result: {result}")

asyncio.run(main())
