import asyncio
import os
import sys

sys.path.append(os.path.join(os.getcwd(), 'api'))
sys.path.append(os.path.join(os.getcwd(), 'convertors'))
from mcp_server import handle_google_drive

async def main():
    content = "# Test Document"
    res = await handle_google_drive(
        operation="upload",
        filename="creator_test.md",
        content=content,
        folder_id="0AAObXJILB1CgUk9PVA"
    )
    for item in res:
        print(item.text)

if __name__ == "__main__":
    asyncio.run(main())
