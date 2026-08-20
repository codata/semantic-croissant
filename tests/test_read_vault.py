import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run():
    server_params = StdioServerParameters(
        command="python",
        args=["api/main.py"],
        env=None
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Initialized")
            result = await session.call_tool("read_vault_article", arguments={
                "url_or_filename": "eu_ai_factories_host_country_and_investment_map_final_UNF-6_mpFcb1f9sTIvzCxWykkqVA_anonymous_20260809_215305.md"
            })
            print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(run())
