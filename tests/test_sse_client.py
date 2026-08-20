import asyncio
import httpx
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from mcp.types import Implementation
import json

async def run():
    url = "http://localhost:7070/sse"
    async with sse_client(url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            print("Initialized SSE connection")
            res = await session.call_tool("save_to_vault", {
                "content": "TEST",
                "prefix": "semantic_croissant_cdif_research_questions_analysis",
                "jsonld_payload": json.dumps({"test": "yes", "creator": [], "isBasedOn": []})
            })
            print(res)

asyncio.run(run())
