import asyncio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
import json

async def main():
    async with sse_client("http://localhost:7070/sse") as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("Initialized session")
            
            payload_arg = json.dumps({"test": "data"})
            content_arg = "Test markdown content"
            
            print("Calling store_in_vault")
            try:
                result = await session.call_tool("store_in_vault", arguments={
                    "jsonld_payload": payload_arg,
                    "content": content_arg,
                    "prefix": "session",
                    "ai_model_override": "gemma4:e4b"
                })
                print(result)
            except Exception as e:
                print(f"Error: {e}")

asyncio.run(main())
