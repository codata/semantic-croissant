import asyncio
import os
import sys

sys.path.append(os.path.join(os.getcwd(), 'api'))
sys.path.append(os.path.join(os.getcwd(), 'convertors'))
import mcp_server

async def main():
    print("Starting...")
    content = "# Test"
    try:
        print("Calling handle_google_drive...")
        res = await mcp_server.handle_google_drive(
            operation="upload",
            filename="native_suggestion_test.md",
            content=content,
            folder_id="0AAObXJILB1CgUk9PVA",
            suggest_mode=True
        )
        print("Call complete!")
        for item in res:
            print(item.text)
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
