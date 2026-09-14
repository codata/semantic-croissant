import asyncio
import httpx
import markdownify

async def run():
    async with httpx.AsyncClient(follow_redirects=True, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}) as client:
        resp = await client.get('https://www.london.gov.uk/climate-change-could-cost-london-36-billion')
        content = markdownify.markdownify(resp.text, heading_style='ATX').strip()
        print(len(content))
        print(content[:500])

asyncio.run(run())
