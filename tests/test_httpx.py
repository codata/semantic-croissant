import asyncio
import httpx

async def main():
    dataset_id_or_url = "https://doi.org/10.7910/DVN/PUWWV9"
    async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": "curl/7.68.0"}) as client:
        import urllib.request
        try:
            req = urllib.request.Request(dataset_id_or_url, method="HEAD", headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req) as resp:
                resolved_url = resp.url
                
            doi_part = None
            base_url = None
            if "dataset.xhtml?persistentId=doi:" in resolved_url:
                base_url = resolved_url.split("/dataset.xhtml")[0]
                doi_part = resolved_url.split("persistentId=")[1].split("&")[0]
            elif "citation?persistentId=doi:" in resolved_url:
                base_url = resolved_url.split("/citation")[0]
                doi_part = resolved_url.split("persistentId=")[1].split("&")[0]
                
            if base_url and doi_part:
                print(f"base_url={base_url}, doi_part={doi_part}")
                croissant_url = f"{base_url}/api/datasets/export?exporter=croissant&persistentId={doi_part}"
                print(f"croissant_url={croissant_url}")
                export_res = await client.get(croissant_url)
                print(f"status={export_res.status_code}")
                if export_res.status_code == 200:
                    print("SUCCESS!")
                else:
                    print("FAILED!")
                    print(export_res.text)
        except Exception as e:
            print(f"Exception: {e}")

asyncio.run(main())
