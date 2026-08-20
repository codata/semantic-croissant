import re
import os
import asyncio
import json
import httpx
import sys
import argparse
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent.config")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

OLLAMA_HOST = config.get("OLLAMA_HOST", "http://10.147.18.82:11435")
MODEL = config.get("MODEL", "gemma4:e4b")
MCP_URL = config.get("MCP_URL", "http://localhost:7070/sse")
AI_MODEL_OVERRIDE = config.get("ai_model_override", "Semantic Croissant AI Agent v.0.1")
SYSTEM_PROMPT = config.get("system_prompt", "You are an autonomous AI data analyst agent connected to an MCP tool ecosystem.")
USER_PROMPT_TEMPLATE = config.get("user_prompt_template", "Execute the user's query: \"{query}\"")

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

async def run_agent(query: str, expert: str = "openml", limit: int = 10, save_vault: bool = False):
    print(f"Connecting to MCP Server at {MCP_URL}...")
    async with sse_client(MCP_URL) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            
            # 1. Fetch available tools dynamically from MCP
            mcp_tools = await session.list_tools()
            ollama_tools = [mcp_tool_to_ollama(t) for t in mcp_tools.tools]
            print(f"Loaded {len(ollama_tools)} tools into the Agent.")
            
            system_prompt = SYSTEM_PROMPT
            user_prompt = USER_PROMPT_TEMPLATE.format(query=query, expert=expert)
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                async def keepalive():
                    try:
                        while True:
                            await asyncio.sleep(15)
                            await session.send_ping()
                    except Exception:
                        pass
                
                keepalive_task = asyncio.create_task(keepalive())
                
                while True:
                    print(f"\n[Agent] Thinking... (Model: {MODEL})")
                    try:
                        response = await client.post(
                            f"{OLLAMA_HOST}/api/chat",
                            json={
                                "model": MODEL,
                                "messages": messages,
                                "tools": ollama_tools,
                                "stream": False,
                                "options": {
                                    "num_ctx": 65536
                                }
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
                                if len(result_str) > 10000:
                                    result_str = result_str[:10000] + "\n...[TRUNCATED due to length]"
                            except Exception as e:
                                result_str = f"Error executing tool: {str(e)}"
                                
                            print(f"📥 [Tool Result]: {result_str[:300]}...\n")
                            
                            messages.append({
                                "role": "tool",
                                "content": result_str,
                                "name": name
                            })
                    else:
                        keepalive_task.cancel()
                        final_answer = msg.get("content", "")
                        print("\n✅ [Agent] Final Answer:")
                        print(final_answer)
                        
                        if save_vault and final_answer.strip():
                            print("\n💾 [Agent Script] Saving final answer to Vault...")
                            
                            # Attempt to find the real JSON-LD generated by the agent's tools
                            jsonld_path_to_pass = None
                            md_path_to_pass = None
                            for m in messages:
                                if m.get("role") == "tool":
                                    if "Output saved to " in m.get("content", ""):
                                        match = re.search(r"Output saved to (.*?\.jsonld)", m["content"])
                                        if match:
                                            jsonld_path_to_pass = match.group(1).strip()
                                    if "Extracted markdown saved to " in m.get("content", ""):
                                        match = re.search(r"Extracted markdown saved to (.*?\.md)", m["content"])
                                        if match:
                                            md_path_to_pass = match.group(1).strip()
                            
                            if jsonld_path_to_pass:
                                try:
                                    import subprocess
                                    cmd = ["docker", "exec", "semantic-croissant-mcp-croissant-live-1", "cat", jsonld_path_to_pass]
                                    payload_arg = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
                                except Exception as e:
                                    print(f"Failed to read JSON-LD from container: {e}")
                                    payload_arg = json.dumps({
                                        "@context": {
                                            "@language": "en",
                                            "@vocab": "https://schema.org/",
                                            "cr": "http://mlcommons.org/croissant/",
                                            "sc": "https://schema.org/"
                                        },
                                        "@type": "cr:Dataset",
                                        "name": f"Agent Output for {query}",
                                        "description": "Automatically saved agent response"
                                    })
                            else:
                                payload_arg = json.dumps({
                                    "@context": {
                                        "@language": "en",
                                        "@vocab": "https://schema.org/",
                                        "cr": "http://mlcommons.org/croissant/",
                                        "sc": "https://schema.org/"
                                    },
                                    "@type": "cr:Dataset",
                                    "name": f"Agent Output for {query}",
                                    "description": "Automatically saved agent response"
                                })
                                
                            content_arg = final_answer
                            if md_path_to_pass:
                                try:
                                    import subprocess
                                    cmd = ["docker", "exec", "semantic-croissant-mcp-croissant-live-1", "cat", md_path_to_pass]
                                    content_arg = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
                                except Exception as e:
                                    print(f"Failed to read markdown from container: {e}")
                            
                            try:
                                save_result = await session.call_tool("save_to_vault", arguments={
                                    "prefix": "agent_script_output",
                                    "content": content_arg,
                                    "jsonld_payload": payload_arg,
                                    "ai_model_override": AI_MODEL_OVERRIDE
                                })
                                save_msg = "\n".join([c.text for c in save_result.content if c.type == "text"])
                                print(f"✅ Saved to Vault:\n{save_msg}")
                            except Exception as e:
                                print(f"❌ Failed to save to Vault programmatically: {e}")
                        break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run an autonomous MCP agent powered by Ollama.")
    parser.add_argument('-q', '--query', type=str, help="The search query to ask the expert (e.g., 'auto sales').")
    parser.add_argument('-e', '--expert', type=str, default='openml', help="The expert index to query (e.g., 'openml', 'dataverse').")
    parser.add_argument('-l', '--limit', type=int, default=10, help="The maximum number of search results to return.")
    parser.add_argument('--save-vault', action='store_true', help="Automatically save the agent's final answer to the vault.")
    
    # Show help by default if no arguments are provided
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
        
    args = parser.parse_args()
    if not args.query:
        print("Error: The -q/--query argument is required.")
        parser.print_help()
        sys.exit(1)
        
    asyncio.run(run_agent(args.query, args.expert, args.limit, args.save_vault))
