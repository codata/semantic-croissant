import asyncio
import os
import sys

sys.path.append(os.path.abspath("api"))
from mcp_server import read_vault_article

async def test_read():
    res = await read_vault_article("HETXv4zTX2TzUOWZvcuNNA.md")
    print(res[0].text[:500])

asyncio.run(test_read())
