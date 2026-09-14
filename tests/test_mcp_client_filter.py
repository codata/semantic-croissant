import asyncio
import json
from mcp.server import Server
from mcp.types import Tool
from mcp.server.lowlevel.server import request_ctx

# We need to load mcp_server.py to get its list_tools implementation
# Let's import list_tools directly
import sys
import os
sys.path.append(os.path.abspath("api"))
from mcp_server import list_tools, call_tool

class MockClientInfo:
    def __init__(self, name):
        self.name = name

class MockSession:
    def __init__(self, name):
        self.client_info = MockClientInfo(name)

class MockContext:
    def __init__(self, name):
        self.session = MockSession(name)

async def test_tools():
    # Test with Claude
    token = request_ctx.set(MockContext("Claude Desktop"))
    try:
        tools = await list_tools()
        has_search = any(t.name == "search_web" for t in tools)
        print(f"Claude has search_web: {has_search}")
    finally:
        request_ctx.reset(token)

    # Test with non-Claude
    token2 = request_ctx.set(MockContext("Antigravity Client"))
    try:
        tools2 = await list_tools()
        has_search2 = any(t.name == "search_web" for t in tools2)
        print(f"Non-Claude has search_web: {has_search2}")
    finally:
        request_ctx.reset(token2)

    # Test the actual tool
    res = await call_tool("search_web", {"query": "test query croissant semantic"})
    print("search_web output:", res[0].text)

asyncio.run(test_tools())
