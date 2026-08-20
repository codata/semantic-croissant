import asyncio
import os
import sys

sys.path.append(os.path.join(os.getcwd(), 'api'))
sys.path.append(os.path.join(os.getcwd(), 'convertors'))
from mcp_server import handle_google_drive

async def main():
    content = """
# Suggestion Parser Test
Here is a raw URL in the text: https://www.google.com
Here is a paragraph with **bold**, *italic*, and [links](https://openai.com).

- Item 1 with **bold**
- Item 2 with *italic*

---
## References
1. https://deepmind.com
2. A citation with a URL https://github.com in the middle.
"""
    res = await handle_google_drive(
        operation="upload",
        filename="native_suggestion_complex.md",
        content=content,
        folder_id="0AAObXJILB1CgUk9PVA",
        suggest_mode=True
    )
    for item in res:
        print(item.text)

if __name__ == "__main__":
    asyncio.run(main())
