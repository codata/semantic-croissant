from mcp.server import Server
app = Server("test")
try:
    ctx = app.request_context
    print(dir(ctx))
except Exception as e:
    print("Error:", e)
