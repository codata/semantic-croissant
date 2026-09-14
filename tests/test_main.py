import asyncio
import httpx
from minio import Minio
from datetime import timedelta
async def stream_file():
    m_client = Minio('localhost:9025', access_key='minioadmin', secret_key='minioadmin', secure=False)
    url = m_client.presigned_get_object('vault', 'ueaGDTjRoC1Y0S55f9qxCA.md', expires=timedelta(hours=1))
    print('URL:', url)
    async with httpx.AsyncClient() as c:
        r = await c.get(url)
        print('Status:', r.status_code)
        print('Content length:', len(r.content))
asyncio.run(stream_file())
