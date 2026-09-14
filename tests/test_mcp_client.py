import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["api/mcp_server.py"]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # test without override
            print("=== Testing without override ===")
            try:
                res = await session.call_tool("save_to_vault", arguments={
                    "prefix": "test_save",
                    "content": "test content",
                    "jsonld_payload": "{}"
                })
                print(res.content[0].text)
            except Exception as e:
                print(e)
                
            # test with override
            print("\n=== Testing with override ===")
            try:
                res = await session.call_tool("save_to_vault", arguments={
                    "prefix": "test_save",
                    "content": "test content",
                    "jsonld_payload": "{}",
                    "ai_model_override": "LM Studio Llama 3"
                })
                print(res.content[0].text)
            except Exception as e:
                print(e)

if __name__ == "__main__":
    asyncio.run(main())
