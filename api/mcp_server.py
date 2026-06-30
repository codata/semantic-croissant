from mcp.server.fastmcp import FastMCP
import httpx
import os

# Initialize FastMCP server
mcp = FastMCP("Croissant MCP")

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
    mcp.run()
