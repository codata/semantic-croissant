import asyncio
from api.mcp_server import handle_google_drive

async def main():
    print("Testing Upload...")
    res = await handle_google_drive(
        operation="upload",
        filename="mcp_test_report.md",
        content="# Test Report\\n\\nThis is a test from MCP tool.\\n",
        folder_id="0AAObXJILB1CgUk9PVA"
    )
    print(res[0].text)

    print("\\nTesting Search...")
    res = await handle_google_drive(
        operation="search",
        query="name contains 'mcp_test_report'",
        folder_id="0AAObXJILB1CgUk9PVA"
    )
    print(res[0].text)
    
    # Extract ID
    file_id = None
    if "ID: " in res[0].text:
        file_id = res[0].text.split("ID: ")[1].split(",")[0]
        
    if file_id:
        print(f"\\nTesting Read for ID {file_id}...")
        res = await handle_google_drive(
            operation="read",
            file_id=file_id
        )
        print(res[0].text[:100] + "...")
        
if __name__ == "__main__":
    asyncio.run(main())
