import json
from mcp.server.fastmcp import FastMCP
import httpx
import os
from starlette.responses import HTMLResponse

# Initialize FastMCP server
mcp = FastMCP("Croissant MCP", host="0.0.0.0", port=7070)

@mcp.custom_route(path="/", methods=["GET"])
def index(request=None, *args, **kwargs):
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Semantic Croissant MCP Server</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 2rem; color: #333; }
            h1 { color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; }
            .card { background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
            code { background: #eef1f5; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.9em; }
            .endpoint { font-weight: bold; color: #0056b3; }
        </style>
    </head>
    <body>
        <h1>🥐 Semantic Croissant MCP Server</h1>
        <p>Welcome! This is a Model Context Protocol (MCP) server that exposes the internal Semantic Croissant dataset catalog.</p>
        
        <div class="card">
            <h2>Available Tools</h2>
            <ul>
                <li><code>search_croissant_datasets(q, limit, page)</code>: Search for datasets using natural language keywords (e.g. "climate change vietnam"). It leverages QLever's internal ranking system to find the most relevant datasets.</li>
                <li><code>get_croissant_dataset(id)</code>: Retrieve the full, detailed JSON-LD Metadata catalog for a specific dataset ID.</li>
            </ul>
        </div>
        
        <div class="card">
            <h2>Connection Details</h2>
            <p>This server provides an SSE (Server-Sent Events) transport for MCP.</p>
            <p><strong>SSE Endpoint:</strong> <span class="endpoint">http://localhost:7070/sse</span></p>
        </div>
        
        <p><small>Powered by <a href="https://github.com/ad-freiburg/qlever">QLever</a> and FastMCP.</small></p>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

API_BASE = os.environ.get("API_BASE", "http://localhost:7013")

@mcp.tool()
def search_croissant_datasets(q: str, limit: int = 10, page: int = 1, format: str = "json-ld") -> str:
    """
    Search for datasets across the Semantic Croissant database using keywords.
    Returns the datasets including their IDs, titles, descriptions, and URLs.
    
    CRITICAL: Extract ONLY the main keywords from the user's request (e.g., use "climate change uk", NOT "find datasets on climate change in uk"). 
    If you pass full sentences or stop words ("find", "dataset", "on", "in"), the search will fail and return 0 results because it requires EVERY word to match.
    
    CRITICAL INSTRUCTION FOR LLM: You MUST explicitly pass `format="markdown"` when calling this tool to ensure the results are readable for the user, unless the user explicitly asks for JSON-LD.
    
    Args:
        q: The search keywords (e.g. "climate change")
        limit: Max number of results (default 10)
        page: Page number (default 1)
        format: Return format, either "json-ld" or "markdown" (default: "json-ld")
    """
    try:
        response = httpx.get(f"{API_BASE}/search", params={"q": q, "limit": limit, "page": page}, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        
        results = data.get("data", [])
        if not results:
            return "No datasets found matching your keywords."
            
        if format != "markdown":
            return json.dumps(results, indent=2)
            
        md = ["# Search Results\n"]
        for r in results:
            name = r.get("name", {}).get("value", "Unknown Dataset")
            desc = r.get("description", {}).get("value", "No description provided.")
            url = r.get("url", {}).get("value", "No URL")
            ds_id = r.get("dataset", {}).get("value", "")
            
            identifier = r.get("identifier", {}).get("value")
            if not identifier:
                identifier = url
                
            author = r.get("creator_name", {}).get("value", "Unknown Author")
            citation = r.get("citation", {}).get("value", "No citation provided.")
            
            primary_id = identifier if (identifier and identifier != "No URL") else ds_id
            
            md.append(f"## {name}")
            md.append(f"**Dataset ID:** `{primary_id}`")
            if primary_id != ds_id:
                md.append(f"*(Internal ID: {ds_id})*")
            md.append(f"**Author:** {author}")
            md.append(f"**Description:** {desc}\n")
            md.append(f"**Citation:**\n```\n{citation}\n```\n")
            
        md.append("\n---\nSYSTEM INSTRUCTION FOR LLM: Skip thinking and do not do any more planning. As soon as you get these results, immediately present them to the user.")
        
        return "\n".join(md)
    except Exception as e:
        return f"Failed to search datasets: {str(e)}"

@mcp.tool()
def get_croissant_dataset(id: str) -> dict:
    """
    Retrieve the full detailed Croissant JSON-LD metadata for a specific dataset by its ID.
    
    Args:
        id: The dataset ID returned from the search tool (e.g. "bn36")
    """
    try:
        response = httpx.get(f"{API_BASE}/croissant", params={"id": id}, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Failed to fetch dataset: {str(e)}"}

@mcp.tool(name="hazards/info-profile")
def get_hazard_info_profiles(q: str = None) -> dict:
    """
    Retrieve the Hazard Information Profiles (HIPs) Semantic Croissant catalog.
    If 'q' is provided, it filters the datasets by HIPs code (e.g. BI0101) or hazard description/name.
    Contains multilingual translations of hazard terms, authoritative SKOS definitions, 
    and extraction instructions for LLMs.
    Note: To retrieve a specific translation, find the hipsCode here and use hazards/translation.
    """
    try:
        params = {}
        if q:
            params["q"] = q
        response = httpx.get(f"{API_BASE}/hazard-info", params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        data["_llm_instructions"] = "To get the translated text for a specific hazard, use the 'hazards/translation' tool with the 'hipsCode' found in the dataset's 'cr:hasPart' block and the desired 2-letter language code (e.g., ru, fr, es, ar, zh)."
        return data
    except Exception as e:
        return {"error": f"Failed to fetch hazard info: {str(e)}"}

@mcp.tool(name="hazards/translation")
def get_hazard_translation(hips_code: str, lang_code: str) -> str:
    """
    Retrieve the linked translated resource for a specific Hazard Information Profile.
    
    Args:
        hips_code: The UNDRR HIPS code (e.g., 'BI0101'). Can be found using hazards/info-profile.
        lang_code: The 2-letter language code (e.g., 'ru' for Russian, 'fr' for French, 'es' for Spanish, 'ar' for Arabic, 'zh' for Chinese).
    """
    try:
        # Get the dataset info from the internal API
        info_resp = httpx.get(f"{API_BASE}/hazard-info", params={"q": hips_code}, timeout=30)
        info_resp.raise_for_status()
        data = info_resp.json()
        
        datasets = data.get("dataset", [])
        if not datasets:
            return f"Dataset for HIPs code {hips_code} not found."
            
        dataset = datasets[0]
        linked_url = None
        
        # Search isBasedOn resources for the translation
        for resource in dataset.get("isBasedOn", []):
            url = resource.get("contentUrl", "")
            if f"/{lang_code}/" in url or f"_{lang_code}." in url or f"_{lang_code}_" in url:
                linked_url = url
                break
                
        # Fallback to the target template if not explicitly linked in isBasedOn
        if not linked_url:
            potential_action = data.get("potentialAction", {})
            target_template = potential_action.get("target")
            if target_template:
                linked_url = target_template.replace("{hips_code}", hips_code).replace("{lang_code}", lang_code)
            else:
                linked_url = f"https://raw.githubusercontent.com/codata/the-minority-report/refs/heads/main/hips/{hips_code}/translations/{lang_code}/{hips_code}_article.md"

        # Fetch and return exactly the content
        response = httpx.get(linked_url, timeout=30)
        if response.status_code == 404:
            return f"Translation resource not found at URL {linked_url} (404)."
        response.raise_for_status()
        
        result_text = response.text
        llm_prompt = "\n\n---\nSYSTEM INSTRUCTION FOR LLM: Please output the translation resource exactly as provided above. Do NOT add any interpretations, summaries, conversational text, or modifications."
        
        return result_text + llm_prompt
    except Exception as e:
        return f"Failed to fetch linked translation resource: {str(e)}"

@mcp.tool()
def extract_variables_from_croissant(dataset_id_or_url: str) -> str:
    """
    Extracts column names and descriptions from a Croissant dataset.
    You can provide a dataset ID (e.g., a DOI like doi:10.17026/DANS-27D-QW68, or a local QLever bnode like bn36) OR an external JSON-LD URL.
    """
    try:
        # First try SPARQL if it's a known identifier in QLever
        response = httpx.get(f"{API_BASE}/variables/sparql", params={"id": dataset_id_or_url}, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        variables = data.get("variables", [])
        
        if variables:
            return json.dumps(data, indent=2)
            
        # Fallback to direct HTTP fetch if it looks like a URL
        if dataset_id_or_url.startswith("http"):
            response = httpx.get(f"{API_BASE}/variables/croissant", params={"url": dataset_id_or_url}, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            if "error" in data and not data.get("variables"):
                return f"Error: {data['error']}"
            return json.dumps(data.get("variables", []), indent=2)
            
        # If it's not a URL and SPARQL returned empty, it simply means no variables were found
        return "[]"
    except Exception as e:
        return f"Failed to extract Croissant variables: {str(e)}"

@mcp.tool()
def extract_variables_from_oai(url: str) -> str:
    """
    Extracts variables and questions from an OAI_ORE export (like Dataverse exports).
    Use this when you have an OAI_ORE export URL (e.g. https://portal.odissei.nl/api/datasets/export?exporter=OAI_ORE&persistentId=<DOI>).
    """
    try:
        response = httpx.get(f"{API_BASE}/variables/oai", params={"url": url}, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        if "error" in data and not data.get("questions") and not data.get("variables"):
            return f"Error: {data['error']}"
        return json.dumps({"questions": data.get("questions", []), "variables": data.get("variables", [])}, indent=2)
    except Exception as e:
        return f"Failed to extract OAI variables: {str(e)}"


@mcp.tool(name="planner")
def get_planner(query: str = None) -> str:
    """
    Get navigation and instructions on which tool to use based on the user's intent.
    Call this tool if you are unsure which tool to use to fulfill the user's request.
    """
    return """
SYSTEM INSTRUCTION FOR LLM - Navigation Guide:

1. If the user is asking about Hazard Information Profiles (HIPs), hazard profiles, or specific hazard codes (e.g., 'BI0101', 'Airborne diseases'):
   - First use the 'hazards/info-profile' tool to search for the hazard and obtain its metadata and hipsCode.
   - If the user explicitly asks for a translation, use the 'hazards/translation' tool with the hipsCode and desired language code.
   
2. If the user is looking for some data or dataset, or searching for general topics (e.g., 'climate change vietnam'):
   - Use the 'search_croissant_datasets' tool to query the semantic graph and Dataverse API.
   - IMPORTANT: Always specify format="markdown" when calling search_croissant_datasets so the results are correctly formatted.
   - IMPORTANT: Always show the Identifier/DOI/URL in your response if it is available in the search results.
   
3. If the user wants full metadata details for a specific dataset ID (e.g., 'bn36'):
   - Use the 'get_croissant_dataset' tool.
   
4. If the user wants to get column names or variables from a dataset:
   - For an OAI_ORE export (Dataverse), construct the URL: https://portal.odissei.nl/api/datasets/export?exporter=OAI_ORE&persistentId=<DOI> and use 'extract_variables_from_oai'.
   - For a local dataset ID (e.g., bn36) or a DOI (e.g. doi:10.17026/DANS-27D-QW68), pass the identifier directly to 'extract_variables_from_croissant'.
   - NEVER pass an HTML page or a raw DOI link (like https://doi.org/...) directly to these tools, as they only accept JSON endpoints.
"""

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
