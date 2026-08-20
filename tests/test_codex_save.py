import asyncio
from mcp.client.sse import sse_client
from mcp import ClientSession

payload = {
  "prefix": "ai_factories_interface_eu",
  "content": "# EU AI Factories -- Numbers & Figures Extracted",
  "jsonld_payload": {
    "@context": "https://schema.org/",
    "@type": "Dataset",
    "name": "EU AI Factories Numbers and Figures"
  }
}

async def main():
    async with sse_client("http://localhost:7070/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Initialized")
            result = await session.call_tool("save_to_vault", payload)
            print(f"Result: {result}")

asyncio.run(main())
