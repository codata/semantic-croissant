import asyncio
from mcp.server import Server
app = Server("test")
async def main():
    try:
        ctx = app.request_context
        print("Success:", ctx)
    except Exception as e:
        print("Error:", repr(e))

asyncio.run(main())
