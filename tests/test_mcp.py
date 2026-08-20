import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json

async def test():
    server_params = StdioServerParameters(
        command="docker",
        args=["exec", "-i", "semantic-croissant-mcp-croissant-live-1", "python", "/app/mcp_server.py"]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Initialized")
            result = await session.call_tool("save_to_vault", {
                "content": "Test content",
                "prefix": "test_script",
                "jsonld_payload": json.dumps({"test": "data", "creator": []})
            })
            print(result)

if __name__ == "__main__":
    asyncio.run(test())
