import mcp
from mcp.server import Server
app = Server("test")
print(type(app.request_context))
