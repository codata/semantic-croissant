import asyncio
import os
import sys

sys.path.append(os.path.abspath("api"))
from mcp_server import store_in_vault

async def test_save():
    try:
        res = await store_in_vault(
            content="test content",
            prefix="test_prefix",
            jsonld_payload=None,
            ai_model_override="Test AI"
        )
        print("Result:", res[0].text)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(test_save())
