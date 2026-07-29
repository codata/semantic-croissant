import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client
import sys

async def main():
    url = "http://localhost:7070/sse"
    print(f"Connecting to MCP server at {url}...")
    
    try:
        async with sse_client(url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("Session initialized successfully.")
                
                # We will test the ingest_to_qlever tool
                # by passing it the relative file path to a known JSON-LD artifact in the workspace.
                test_file = "www_youtube_com_watch_croissant.jsonld"
                
                with open(test_file, "r") as f:
                    payload = f.read()
                
                print(f"\nCalling ingest_to_qlever with jsonld_payload (size {len(payload)} bytes), rebuild=False...")
                result = await session.call_tool("ingest_to_qlever", {
                    "jsonld_payload": payload,
                    "rebuild": False
                })
                
                print("\n--- Result ---")
                for content in result.content:
                    if hasattr(content, 'text'):
                        print(content.text)
                    else:
                        print(content)
                        
    except Exception as e:
        print(f"Error during MCP connection or execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
