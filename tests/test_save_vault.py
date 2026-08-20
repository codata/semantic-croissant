import asyncio
from mcp.client.sse import sse_client
from mcp import ClientSession

async def main():
    async with sse_client("http://localhost:7070/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Initialized")
            result = await session.call_tool("save_to_vault", {
                "content": "Test content",
                "prefix": "test_prefix",
                "jsonld_payload": {"@context": "test", "@type": "Dataset"}
            })
            print(f"Result: {result}")

asyncio.run(main())
