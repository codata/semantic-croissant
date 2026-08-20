import asyncio
import os
import sys

sys.path.append(os.path.join(os.getcwd(), 'api'))
sys.path.append(os.path.join(os.getcwd(), 'convertors'))
from mcp_server import handle_google_drive, read_vault_article

async def main():
    print("Reading file from Vault using MCP tool...")
    filename = "session_UNF-6_jSFVkZMD0xV7s1vSUw60w_UNF-6_jSFVkZMD0xV7s1vSUw60w_did_zqmqr5ap_20260816_125225.md"
    
    try:
        res = await read_vault_article(filename)
        content = res[0].text
    except Exception as e:
        print(f"Error reading file from Vault: {e}")
        return

    print("Uploading file via MCP handler with suggest_mode=True...")
    res = await handle_google_drive(
        operation="upload",
        filename="suggested_report.md",
        content=content,
        folder_id="0AAObXJILB1CgUk9PVA",
        suggest_mode=True
    )
    
    print("Response from MCP Tool:")
    for content_item in res:
        print(content_item.text)

if __name__ == "__main__":
    asyncio.run(main())
