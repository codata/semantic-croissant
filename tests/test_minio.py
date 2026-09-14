from minio import Minio
from datetime import timedelta
import httpx
import asyncio

async def test():
    m_client = Minio("localhost:9025", access_key="minioadmin", secret_key="minioadmin", secure=False)
    url = m_client.presigned_get_object("vault", "ueaGDTjRoC1Y0S55f9qxCA.md", expires=timedelta(hours=1))
    print("URL:", url)
    async with httpx.AsyncClient() as c:
        r = await c.get(url)
        print("Status:", r.status_code)
        
asyncio.run(test())
