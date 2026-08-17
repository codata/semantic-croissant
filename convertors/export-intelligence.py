import argparse
import os
import re
import json
import urllib.request
import urllib.error

def download_file(url):
    print(f"Downloading {url} ...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            return response.read().decode('utf-8')
    except urllib.error.URLError as e:
        print(f"Failed to download {url}: {e}")
        return None

def process_exports(vault_url, github_repo, branch, folder):
    # Ensure github_repo doesn't end with slash
    github_repo = github_repo.rstrip('/')
    
    # Extract the base filename
    base_filename = vault_url.split('/')[-1]
    base_name = base_filename
    if base_name.endswith('.md'):
        base_name = base_name[:-3]
    elif base_name.endswith('.jsonld'):
        base_name = base_name[:-7]
        
    vault_base_url = vault_url.rsplit('/', 1)[0]
    
    # We will gather a set of files to download and process
    # Each item is just the filename
    files_to_process = set()
    files_to_process.add(f"{base_name}.md")
    files_to_process.add(f"{base_name}.jsonld")
    
    # First pass: download the main jsonld to find history files
    main_jsonld_url = f"{vault_base_url}/{base_name}.jsonld"
    jsonld_content = download_file(main_jsonld_url)
    
    if jsonld_content:
        try:
            data = json.loads(jsonld_content)
            # Find isBasedOn
            is_based_on = data.get("isBasedOn", [])
            if isinstance(is_based_on, dict):
                is_based_on = [is_based_on]
                
            for item in is_based_on:
                if isinstance(item, dict) and "url" in item:
                    item_url = item["url"]
                    if vault_base_url in item_url:
                        history_filename = item_url.split('/')[-1]
                        files_to_process.add(history_filename)
                        # also try to grab the corresponding jsonld if it's an md
                        if history_filename.endswith('.md'):
                            files_to_process.add(history_filename[:-3] + '.jsonld')
        except json.JSONDecodeError:
            print(f"Warning: Failed to parse JSON-LD from {main_jsonld_url}")

    # Create local output folder
    out_dir = folder if folder else "export"
    os.makedirs(out_dir, exist_ok=True)

    # Base github url for replacing links
    # e.g., https://github.com/CA4EOSC/consortium/blob/main/UseCases/
    if folder:
        github_blob_base = f"{github_repo}/blob/{branch}/{folder}"
    else:
        github_blob_base = f"{github_repo}/blob/{branch}"

    downloaded_contents = {}

    # Second pass: download all discovered files
    for filename in list(files_to_process):
        file_url = f"{vault_base_url}/{filename}"
        content = download_file(file_url)
        if content:
            downloaded_contents[filename] = content
            
            # Also scan markdown files for any other vault links just in case
            if filename.endswith('.md'):
                # find all https://mcp.dev.codata.org/vault/...md links
                vault_links = re.findall(r'https://mcp\.dev\.codata\.org/vault/[a-zA-Z0-9_\-\.]+', content)
                for link in vault_links:
                    linked_filename = link.split('/')[-1]
                    if linked_filename not in files_to_process and linked_filename not in downloaded_contents:
                        print(f"Discovered additional linked file: {linked_filename}")
                        files_to_process.add(linked_filename)
                        
                        # Fetch it immediately
                        linked_content = download_file(f"{vault_base_url}/{linked_filename}")
                        if linked_content:
                            downloaded_contents[linked_filename] = linked_content
                            if linked_filename.endswith('.md'):
                                # try getting its jsonld too
                                lj = linked_filename[:-3] + '.jsonld'
                                files_to_process.add(lj)
                                lj_content = download_file(f"{vault_base_url}/{lj}")
                                if lj_content:
                                    downloaded_contents[lj] = lj_content

    # Third pass: process contents to replace URLs and save locally
    for filename, content in downloaded_contents.items():
        # Replace the vault base URL with the GitHub blob base URL
        # For .md links inside the markdown files
        # Also replace in JSON-LD fields (url, contentUrl, etc)
        
        # We replace exactly the vault URLs with the github blob URLs
        # Note: vault URLs are typically https://mcp.dev.codata.org/vault/filename.ext
        
        # Regex to find vault URLs and replace with github base
        # Replace: https://mcp.dev.codata.org/vault/ -> https://github.com/.../blob/main/UseCases/
        
        # We should use the actual vault_base_url
        modified_content = content.replace(f"{vault_base_url}/", f"{github_blob_base}/")
        
        # Sometimes URLs might not have trailing slash depending on how we matched, but vault URLs do.
        # Ensure we also replace raw vault url if it appears
        default_vault_base = "https://mcp.dev.codata.org/vault"
        if vault_base_url != default_vault_base:
            modified_content = modified_content.replace(f"{default_vault_base}/", f"{github_blob_base}/")

        out_path = os.path.join(out_dir, filename)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
            
        print(f"Saved modified {filename} to {out_path}")
        
    print(f"\nAll files have been successfully processed and saved in '{out_dir}'.")
    print(f"They are now ready to be committed and pushed to {github_repo}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export intelligence from Vault to a local folder prepared for GitHub publishing.")
    parser.add_argument("vault_url", help="Link to the vault file (e.g., https://mcp.dev.codata.org/vault/filename.md)")
    parser.add_argument("github_repo", help="Link to the GitHub repo (e.g., https://github.com/CA4EOSC/consortium)")
    parser.add_argument("--branch", default="main", help="GitHub branch (default: main)")
    parser.add_argument("--folder", default="", help="Folder inside the GitHub repo (e.g., UseCases)")
    
    args = parser.parse_args()
    process_exports(args.vault_url, args.github_repo, args.branch, args.folder)
