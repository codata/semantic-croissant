import httpx
import asyncio

async def test():
    client = httpx.AsyncClient()
    req = client.build_request('GET', 'http://10.147.18.82:11435', headers={'user-agent': 'curl/8.12.1'}, content=b'')
    resp = await client.send(req)
    print(resp.status_code)

asyncio.run(test())
