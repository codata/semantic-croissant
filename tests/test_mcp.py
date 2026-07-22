import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Croissant MCP", host="0.0.0.0", port=7070)
@mcp.tool()
def test_tool() -> str:
    return "test"

if __name__ == "__main__":
    mcp.run(transport="sse")
