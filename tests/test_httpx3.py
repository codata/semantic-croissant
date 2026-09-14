import httpx
import asyncio

async def test():
    client = httpx.AsyncClient()
    req = client.build_request('GET', 'http://10.147.18.82:11435', content=b'')
    try:
        resp = await client.send(req)
        print(resp.status_code)
    except Exception as e:
        print(f"Error GET with content: {e}")
        
    req = client.build_request('HEAD', 'http://10.147.18.82:11435', content=b'')
    try:
        resp = await client.send(req)
        print(resp.status_code)
    except Exception as e:
        print(f"Error HEAD with content: {e}")

asyncio.run(test())
