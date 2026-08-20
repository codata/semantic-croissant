import asyncio
import os
import sys
import re

# Ensure api directory is in python path to import mcp_server
sys.path.append(os.path.join(os.getcwd(), 'api'))

# Default to localhost if running outside docker, else minio
if "MINIO_URL" not in os.environ:
    if os.path.exists("/.dockerenv"):
        os.environ["MINIO_URL"] = "http://minio:9000"
    else:
        os.environ["MINIO_URL"] = "http://localhost:9000"

from mcp_server import call_tool

async def main():
    if len(sys.argv) < 2:
        print("Usage: python test_honduras_agent.py <query>")
        print("Example: python test_honduras_agent.py 'president charges'")
        sys.exit(1)
        
    query = " ".join(sys.argv[1:])
    print(f"--- 1. Ask Honduras expert about: '{query}' ---")
    response_expert = await call_tool("ask_expert", {"index": "honduras", "q": query})
    text_result = response_expert[0].text
    
    # Extract vault links
    print("\n--- 2. Get links from vault and perform factual analysis ---")
    lines = text_result.split('\n')
    vault_links = []
    for line in lines:
        if line.startswith("Vault Source: "):
            vault_links.append(line.replace("Vault Source: ", "").strip())
    
    if not vault_links:
        print("No vault links found for this query.")
        return
        
    print(f"Found {len(vault_links)} links, analyzing all materials to extract facts...")
    
    summary = f"# Comprehensive Factual Analysis: {query.title()}\n\n"
    summary += f"This document provides a factual synthesis based on {len(vault_links)} vault materials.\n\n"
    
    sources = []
    
    for idx, link in enumerate(vault_links):
        print(f"Reading vault article {idx+1}/{len(vault_links)}: {link}")
        res = await call_tool("read_vault_article", {"url_or_filename": link})
        content = res[0].text
        if content.startswith("Error"):
            continue
            
        content_lines = content.split('\n')
        
        # Extract title
        title = "Unknown Source"
        for line in content_lines[:10]:
            if line.strip() and not line.startswith('#') and not line.startswith('|') and not line.startswith('['):
                title = line.strip()
                break
                
        sources.append(f"{idx+1}. **{title}** - ({link})")
        
        summary += f"## Source {idx+1}: {title}\n"
        
        # Extract sentences with factual numbers
        text_body = content.replace('\n', ' ')
        sentences = re.split(r'(?<=[.!?]) +', text_body)
        
        facts_found = 0
        summary += "**Key Facts & Figures:**\n"
        for s in sentences:
            s_clean = s.strip()
            # If sentence has numbers, is substantial, and doesn't look like boilerplate
            if re.search(r'\d+', s_clean) and len(s_clean) > 30:
                if 'http' not in s_clean and 'Subscribe' not in s_clean and 'Cookie' not in s_clean:
                    summary += f"- {s_clean}\n"
                    facts_found += 1
            if facts_found >= 7: # Limit to top 7 facts per article
                break
                
        if facts_found == 0:
            summary += "- No major numerical figures extracted from this source.\n"
        summary += "\n"
        
    summary += "---\n### References / URLs\n"
    summary += "\n".join(sources)
    
    print("\n--- 3. Ask Honduras expert to save result ---")
    safe_query = query.replace(" ", "_").replace("'", "").replace('"', "").lower()
    save_res = await call_tool("save_to_vault", {"content": summary, "prefix": f"honduras_{safe_query}_factual_summary"})
    print(save_res[0].text)

asyncio.run(main())
