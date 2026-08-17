import os
import requests
import json
import time
import argparse
import urllib.parse
import boto3
import gzip
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_dataset_ids(limit=1000, offset=0):
    url = f"https://www.openml.org/api/v1/json/data/list/limit/{limit}/offset/{offset}"
    for attempt in range(10):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 412:
                return []
            response.raise_for_status()
            data = response.json()
            if "data" in data and "dataset" in data["data"]:
                return [ds["did"] for ds in data["data"]["dataset"]]
        except Exception as e:
            if attempt == 9:
                print(f"Error fetching dataset list (offset {offset}): {e}")
            import time
            time.sleep((2 ** attempt) + 1)
    return []

def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url="http://localhost:9005",
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin"
    )

def ensure_bucket(s3_client, bucket_name="vault"):
    try:
        s3_client.create_bucket(Bucket=bucket_name)
    except Exception:
        pass
    try:
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicRead",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                }
            ]
        }
        s3_client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
    except Exception:
        pass

def fetch_with_retry(url, max_retries=10):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 404:
                return response
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep((2 ** attempt) + 1) # Exponential backoff
    return None

def process_vault_and_save(did, data, output_file, s3_client):
    # Check if we already added isBasedOn properly
    if "isBasedOn" in data:
        # We always want to rebuild the vault file to include the latest Qualities, so we remove the old vault entry
        is_based = data["isBasedOn"]
        if isinstance(is_based, list):
            # Remove all vault/www_openml_org entries
            data["isBasedOn"] = [b for b in is_based if not (isinstance(b, dict) and b.get("contentUrl", "").find("vault/www_openml_org") != -1)]
            if not data["isBasedOn"]:
                del data["isBasedOn"]
        elif isinstance(is_based, dict):
            if is_based.get("contentUrl", "").find("vault/www_openml_org") != -1:
                del data["isBasedOn"]

    # 1. Get Markdown content
    description = data.get("description", "")
    if not description:
        description = f"No description available for OpenML dataset {did}"
        
    # Inject Croissant metadata link into vault's header markdown
    croissant_url = f"https://www.openml.org/croissant/dataset/{did}"
    header = f"# OpenML Dataset {did}\n\n* **Croissant Metadata**: [JSON-LD]({croissant_url})\n\n"
    description = header + description
        
    # Append qualities from the OpenML API
    qualities_url = f"https://www.openml.org/api/v1/json/data/qualities/{did}"
    try:
        q_res = fetch_with_retry(qualities_url)
        if q_res and q_res.status_code == 200:
            q_data = q_res.json()
            qualities = q_data.get("data_qualities", {}).get("quality", [])
            if qualities:
                description += f"\n\n### Qualities ({len(qualities)})\n\n"
                for q in qualities:
                    description += f"* **{q['name']}**: {q['value']}\n"
    except Exception as e:
        print(f"[{did}] Warning: Failed to fetch qualities: {e}")
    
    # Fetch the original dataset metadata to get original_data_url (sameAs)
    if "sameAs" not in data:
        metadata_url = f"https://www.openml.org/api/v1/json/data/{did}"
        try:
            m_res = fetch_with_retry(metadata_url)
            if m_res and m_res.status_code == 200:
                m_data = m_res.json()
                original_url = m_data.get("data_set_description", {}).get("original_data_url")
                if original_url:
                    data["sameAs"] = original_url
        except Exception as e:
            print(f"[{did}] Warning: Failed to fetch metadata for sameAs: {e}")
            
    # 2. Write to local markdown and gzip
    url_str = f"https://www.openml.org/search?type=data&sort=runs&status=active&id={did}"
    parsed_url = urllib.parse.urlparse(url_str)
    safe_name = parsed_url.netloc + parsed_url.path
    safe_name = safe_name.replace("/", "_").replace(".", "_")
    if parsed_url.query:
        qs = urllib.parse.parse_qsl(parsed_url.query)
        for k, v in qs:
            safe_name += "_" + v
    md_filename = f"{safe_name}_content.md"
    gz_filename = f"{md_filename}.gz"
    
    gz_data = gzip.compress(description.encode("utf-8"))
    
    # 3. Upload to MinIO vault
    s3_url = f"https://mcp.dev.codata.org/vault/{gz_filename}"
    try:
        s3_client.put_object(
            Bucket="vault",
            Key=gz_filename,
            Body=gz_data,
            ContentType="application/gzip"
        )
    except Exception as e:
        print(f"[{did}] Warning: Failed to upload to vault: {e}")
        s3_url = f"file://{os.path.abspath(gz_filename)}"
        
    # 4. Add isBasedOn
    based_on_entry = {
        "@type": "CreativeWork",
        "name": "Scraped Markdown Content",
        "url": url_str,
        "contentUrl": s3_url,
        "encodingFormat": "text/markdown",
        "contentEncoding": "gzip"
    }
    
    if "isBasedOn" not in data:
        data["isBasedOn"] = []
    elif not isinstance(data["isBasedOn"], list):
        data["isBasedOn"] = [data["isBasedOn"]]
        
    data["isBasedOn"].append(based_on_entry)
    
    # Also scrape and upload sameAs to vault
    original_url = data.get("sameAs")
    if original_url:
        import re
        has_sameas_vault = False
        for b in data["isBasedOn"]:
            if isinstance(b, dict) and b.get("url") == original_url:
                has_sameas_vault = True
                break
        
        if not has_sameas_vault:
            print(f"[{did}] Scraping sameAs URL: {original_url}")
            jina_url = f"https://r.jina.ai/{original_url}"
            try:
                j_res = fetch_with_retry(jina_url)
                if j_res and j_res.status_code == 200:
                    sameas_md = j_res.text
                    
                    parsed_sameas = urllib.parse.urlparse(original_url)
                    safe_sameas = parsed_sameas.netloc + parsed_sameas.path
                    if parsed_sameas.query:
                        safe_sameas += "_" + parsed_sameas.query
                    safe_sameas = re.sub(r'[^a-zA-Z0-9]', '_', safe_sameas)
                    
                    sameas_filename = f"{safe_sameas}_content.md.gz"
                    sameas_gz = gzip.compress(sameas_md.encode("utf-8"))
                    
                    sameas_s3_url = f"https://mcp.dev.codata.org/vault/{sameas_filename}"
                    try:
                        s3_client.put_object(
                            Bucket="vault",
                            Key=sameas_filename,
                            Body=sameas_gz,
                            ContentType="application/gzip"
                        )
                    except Exception as e:
                        print(f"[{did}] Warning: Failed to upload sameAs to vault: {e}")
                        sameas_s3_url = f"file://{os.path.abspath(sameas_filename)}"
                        
                    sameas_based_on = {
                        "@type": "CreativeWork",
                        "name": "Scraped Markdown Content",
                        "url": original_url,
                        "contentUrl": sameas_s3_url,
                        "encodingFormat": "text/markdown",
                        "contentEncoding": "gzip"
                    }
                    data["isBasedOn"].append(sameas_based_on)
            except Exception as e:
                print(f"[{did}] Warning: Failed to scrape sameAs url: {e}")
    
    # 5. Save back
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        
    return True

def fetch_croissant(did, output_dir):
    output_file = os.path.join(output_dir, f"openml_{did}_croissant.jsonld")
    
    s3_client = get_s3_client()
    
    # If file already exists, we load it and check if it needs vault update
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if "isBasedOn" in data and "sameAs" in data:
                # If it already has both, we can safely skip to speed up processing
                return True
            elif "isBasedOn" in data:
                # Update existing (forces regeneration to include qualities and sameAs)
                process_vault_and_save(did, data, output_file, s3_client)
                return True
            else:
                # Update existing
                process_vault_and_save(did, data, output_file, s3_client)
                return True
        except Exception as e:
            print(f"[{did}] Failed processing existing file: {e}")
            pass # Fallthrough and re-download if file is corrupted

    # Download new file
    url = f"https://www.openml.org/croissant/dataset/{did}"
    try:
        response = fetch_with_retry(url)
        if response.status_code == 404:
            print(f"[{did}] Not found (404).")
            return False
            
        data = response.json()
        process_vault_and_save(did, data, output_file, s3_client)
            
        print(f"[{did}] Successfully downloaded and added to vault.")
        return True
    except Exception as e:
        print(f"[{did}] Failed to fetch: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Harvest Croissant records from OpenML")
    parser.add_argument("--output", type=str, default="./data/openml", help="Output directory")
    parser.add_argument("--limit", type=int, default=1000, help="Number of datasets to fetch per batch")
    parser.add_argument("--max-datasets", type=int, default=None, help="Maximum number of datasets to fetch overall")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent workers")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    
    # Initialize vault
    s3_client = get_s3_client()
    ensure_bucket(s3_client, "vault")
    
    all_dids = []
    offset = 0
    print("Fetching dataset IDs from OpenML...")
    while True:
        dids = get_dataset_ids(limit=args.limit, offset=offset)
        if not dids:
            break
        all_dids.extend(dids)
        print(f"Found {len(all_dids)} datasets so far...")
        offset += args.limit
        if args.max_datasets and len(all_dids) >= args.max_datasets:
            all_dids = all_dids[:args.max_datasets]
            break

    print(f"Total datasets found: {len(all_dids)}")
    print(f"Downloading/Updating Croissant records to {args.output}...")
    
    success_count = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_did = {executor.submit(fetch_croissant, did, args.output): did for did in all_dids}
        
        for i, future in enumerate(as_completed(future_to_did)):
            did = future_to_did[future]
            try:
                if future.result():
                    success_count += 1
                if (i + 1) % 500 == 0:
                    print(f"Processed {i+1}/{len(all_dids)} records...")
            except Exception as e:
                print(f"[{did}] Unhandled exception: {e}")
                
    print(f"Finished downloading. Successfully fetched/updated {success_count}/{len(all_dids)} records.")

if __name__ == "__main__":
    main()
