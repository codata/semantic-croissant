import asyncio
from mcp.server.lowlevel import Server

app = Server("Test")

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    ctx = app.request_context.get()
    print("CTX:", ctx)
    if hasattr(ctx, 'session'):
        print("Session:", ctx.session)
        if hasattr(ctx.session, 'client_params'):
            print("Client params:", ctx.session.client_params)

async def main():
    # simulate?
    pass

if __name__ == "__main__":
    asyncio.run(main())
