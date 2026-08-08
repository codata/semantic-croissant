import asyncio
import json
import httpx
import sys
import argparse
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

OLLAMA_HOST = "http://10.147.18.82:11435"
MODEL = "gemma4:e4b"
MCP_URL = "http://localhost:7070/sse"

def mcp_tool_to_ollama(tool):
    """Convert an MCP Tool schema to Ollama's Chat Completion tool schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
        }
    }

async def run_agent(query: str, expert: str = "openml", limit: int = 10):
    print(f"Connecting to MCP Server at {MCP_URL}...")
    async with sse_client(MCP_URL) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            
            # 1. Fetch available tools dynamically from MCP
            mcp_tools = await session.list_tools()
            ollama_tools = [mcp_tool_to_ollama(t) for t in mcp_tools.tools]
            print(f"Loaded {len(ollama_tools)} tools into the Agent.")
            
            system_prompt = (
                "You are an autonomous AI data analyst agent connected to an MCP tool ecosystem. "
                "You execute instructions by chaining tools together. Always examine tool outputs to decide your next step.\n"
                "CRITICAL: When generating a jsonld_payload for Croissant, you MUST use the Croissant ML format context, NOT standard schema.org. "
                "Your payload must include: \"@context\": {\"@language\": \"en\", \"@vocab\": \"https://schema.org/\", \"cr\": \"http://mlcommons.org/croissant/\", \"sc\": \"https://schema.org/\"}"
            )
            user_prompt = f"""
Execute the following steps:
1. Use the 'ask_expert' tool to search the '{expert}' index for '{query}' and set the 'limit' parameter to {limit}.
2. Find the ID or URL of the very first dataset in the search results, and pass it into the 'extract_variables_from_croissant' tool.
3. Save the results to the vault using the 'save_to_vault' tool. Ensure you generate and include the full 'jsonld_payload' alongside the markdown summary! The JSON-LD MUST be in MLCommons Croissant format.
4. Finally, use the 'list_vault_documents' or similar tool to verify the save was successful.
"""
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                while True:
                    print(f"\n[Agent] Thinking... (Model: {MODEL})")
                    try:
                        response = await client.post(
                            f"{OLLAMA_HOST}/api/chat",
                            json={
                                "model": MODEL,
                                "messages": messages,
                                "tools": ollama_tools,
                                "stream": False
                            }
                        )
                    except Exception as e:
                        print(f"Failed to connect to Ollama: {e}")
                        break
                        
                    if response.status_code != 200:
                        print("Error from Ollama:", response.text)
                        break
                        
                    res_json = response.json()
                    msg = res_json.get("message", {})
                    messages.append(msg)
                    
                    if "tool_calls" in msg and msg["tool_calls"]:
                        for tc in msg["tool_calls"]:
                            fn = tc["function"]
                            name = fn["name"]
                            args = fn["arguments"]
                            print(f"\n🛠️ [Agent] Executing Tool: {name}")
                            print(f"   Arguments: {json.dumps(args, indent=2)}")
                            
                            # Execute the tool via the active MCP connection
                            try:
                                tool_result = await session.call_tool(name, arguments=args)
                                # Extract text content from the MCP response
                                result_str = "\n".join([c.text for c in tool_result.content if c.type == "text"])
                            except Exception as e:
                                result_str = f"Error executing tool: {str(e)}"
                                
                            print(f"📥 [Tool Result]: {result_str[:300]}...\n")
                            
                            messages.append({
                                "role": "tool",
                                "content": result_str,
                                "name": name
                            })
                    else:
                        print("\n✅ [Agent] Final Answer:")
                        print(msg.get("content", ""))
                        break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run an autonomous MCP agent powered by Ollama.")
    parser.add_argument('-q', '--query', type=str, help="The search query to ask the expert (e.g., 'auto sales').")
    parser.add_argument('-e', '--expert', type=str, default='openml', help="The expert index to query (e.g., 'openml', 'dataverse').")
    parser.add_argument('-l', '--limit', type=int, default=10, help="The maximum number of search results to return.")
    
    # Show help by default if no arguments are provided
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
        
    args = parser.parse_args()
    if not args.query:
        print("Error: The -q/--query argument is required.")
        parser.print_help()
        sys.exit(1)
        
    asyncio.run(run_agent(args.query, args.expert, args.limit))
