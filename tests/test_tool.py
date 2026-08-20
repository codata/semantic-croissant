import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import sys

async def main():
    server_params = StdioServerParameters(
        command="docker",
        args=["exec", "-i", "semantic-croissant-mcp-croissant-live-1", "python3", "/app/mcp_server.py", "--stdio"],
        env=None
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Initialized")
            result = await session.call_tool("extract_variables_from_croissant", {"dataset_id_or_url": "https://doi.org/10.7910/DVN/PUWWV9"})
            print(f"Result: {result}")

asyncio.run(main())
