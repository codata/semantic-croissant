import asyncio
import os
import sys

sys.path.append(os.path.join(os.getcwd(), 'api'))
from mcp_server import extract_variables_from_oai

async def main():
    url = "https://dataverse.harvard.edu/api/datasets/export?exporter=OAI_ORE&persistentId=doi:10.7910/DVN/XVFCX0"
    res = await extract_variables_from_oai(url)
    for item in res:
        print(item.text)

if __name__ == "__main__":
    asyncio.run(main())
