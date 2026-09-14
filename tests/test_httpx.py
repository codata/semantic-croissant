import asyncio
import httpx

async def test():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://10.147.18.82:11435/")
            print(resp.status_code)
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())
