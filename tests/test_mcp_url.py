import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def main():
    url = "http://localhost:7070/sse"
    print(f"Connecting to MCP server at {url}...")
    
    try:
        async with sse_client(url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("Session initialized successfully.")
                
                print("\nCalling url_to_croissant via MCP...")
                result = await session.call_tool("url_to_croissant", {
                    "url": "https://data.marine.copernicus.eu/product/GLOBAL_ANALYSISFORECAST_PHY_001_024/description",
                    "slice": True,
                    "traverse": True
                })
                
                print("\n--- Result ---")
                for content in result.content:
                    if hasattr(content, 'text'):
                        print(content.text)
                    else:
                        print(content)
    except Exception as e:
        print(f"Error during MCP connection or execution: {e}")

if __name__ == "__main__":
    asyncio.run(main())
