import asyncio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
import json

import httpx

async def main():
    async with sse_client("http://localhost:7070/sse", timeout=300.0) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("Initialized session")
            
            print("Calling extract_keyfigures")
            try:
                result = await session.call_tool("extract_keyfigures", arguments={
                    "file_path": "https://www.london.gov.uk/climate-change-could-cost-london-36-billion"
                })
                print("--- MCP RESULT ---")
                print(result)
            except Exception as e:
                print(f"Error: {e}")

asyncio.run(main())
