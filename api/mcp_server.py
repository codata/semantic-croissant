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
def search_croissant_datasets(q: str, limit: int = 10, page: int = 1) -> dict:
    """
    Search for datasets across the Semantic Croissant database using keywords.
    Returns the datasets including their IDs, titles, descriptions, and URLs.
    
    Args:
        q: The search query/keywords (e.g. "climate change")
        limit: Max number of results (default 10)
        page: Page number (default 1)
    """
    try:
        response = httpx.get(f"{API_BASE}/search", params={"q": q, "limit": limit, "page": page})
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Failed to search datasets: {str(e)}"}

@mcp.tool()
def get_croissant_dataset(id: str) -> dict:
    """
    Retrieve the full detailed Croissant JSON-LD metadata for a specific dataset by its ID.
    
    Args:
        id: The dataset ID returned from the search tool (e.g. "bn36")
    """
    try:
        response = httpx.get(f"{API_BASE}/croissant", params={"id": id})
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Failed to fetch dataset: {str(e)}"}

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
