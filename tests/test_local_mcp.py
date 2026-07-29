import asyncio
import httpx
import json

async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Connecting to local MCP SSE endpoint...")
        try:
            headers = {"Accept": "text/event-stream"}
            async with client.stream("GET", "http://localhost:7070/sse", headers=headers) as response:
                print("Connected! Headers:", response.headers)
                return
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
