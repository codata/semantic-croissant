import asyncio
import os
import sys

sys.path.append(os.path.join(os.getcwd(), 'api'))
from mcp_server import ask_expert

async def main():
    res = await ask_expert(index="dataverse", q="Malawi data", limit=10)
    for item in res:
        print(item.text)

if __name__ == "__main__":
    asyncio.run(main())
