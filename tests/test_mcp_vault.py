import asyncio
import os
import sys

sys.path.append(os.path.join(os.getcwd(), 'api'))
if "MINIO_URL" not in os.environ:
    os.environ["MINIO_URL"] = "http://localhost:9000"
from mcp_server import call_tool

async def main():
    res = await call_tool("read_vault_article", {"url_or_filename": "honduras_president_charges_factual_summary_20260805_143241.md"})
    print(res[0].text[:200])

asyncio.run(main())
