import os
from mcp.server.fastmcp import FastMCP
from starlette.responses import HTMLResponse

mcp = FastMCP("Croissant MCP", host="0.0.0.0", port=7070)

@mcp.custom_route(path="/", methods=["GET"])
def index():
    return HTMLResponse("<h1>Croissant MCP Server</h1>")

if __name__ == "__main__":
    mcp.run(transport="sse")
