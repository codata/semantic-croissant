import asyncio
import httpx
import json
import re

async def main():
    # Use a simple client for session discovery and tool calling
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Connecting to MCP SSE endpoint...")
        try:
            # Try to get the sessionId via headers on the /mcp endpoint
            headers = {"Accept": "text/event-stream"}
            
            # Using stream to avoid blocking on the infinite SSE body
            async with client.stream("GET", "https://mcp.dev.codata.org/mcp", headers=headers) as response:
                session_id = response.headers.get("mcp-session-id")

                if not session_id:
                    print("Session ID not found in headers.")
                    print("Headers:", response.headers)
                    return

                print(f"Established Session ID: {session_id}")

                # According to the MCP protocol, we must send an initialize request first
                init_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "test_mcp_client",
                            "version": "1.0.0"
                        }
                    }
                }
                
                post_headers = {
                    "mcp-session-id": session_id,
                    "Accept": "application/json, text/event-stream"
                }
                
                print("Sending initialize request...")
                init_res = await client.post("https://mcp.dev.codata.org/mcp", json=init_payload, headers=post_headers)
                if init_res.status_code != 200 or "error" in init_res.json():
                    print(f"Failed to initialize: {init_res.text}")
                    return
                
                # Send the initialized notification
                init_notif = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {}
                }
                await client.post("https://mcp.dev.codata.org/mcp", json=init_notif, headers=post_headers)
                
                print("Initialization complete. Querying tools...")

                # 2. Call the tool 'search_croissant_datasets'
                payload = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "search_croissant_datasets",
                        "arguments": {
                            "q": "climate change",
                            "limit": 5
                        }
                    }
                }

                url = f"https://mcp.dev.codata.org/mcp?sessionId={session_id}"
                print(f"Querying tool 'search_croissant_datasets' at {url}...")
                
                res = await client.post("https://mcp.dev.codata.org/mcp", json=payload, headers=post_headers)
                
                if res.status_code == 200:
                    print("\n--- Search Results ---")
                    print(json.dumps(res.json(), indent=2))
                else:
                    print(f"Error calling tool: {res.status_code}")
                    print(res.text)

        except Exception as e:
            print(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
