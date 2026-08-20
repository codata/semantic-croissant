import requests
import cloudscraper

# Global cloudscraper instance to bypass Cloudflare
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)
import json
import time
import argparse
import urllib.parse
import os
import re
import csv
import io
from bs4 import BeautifulSoup
import markdownify
from rdflib import Graph
from youtube_transcript_api import YouTubeTranscriptApi
from playwright.sync_api import sync_playwright

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
MODEL_NAME = "gemma4-croissant"

def fetch_with_playwright(url):
    print(f"  -> Fetching with Playwright fallback: {url}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(5000)
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        print(f"  -> Playwright fallback failed: {e}")
        return None

def fetch_youtube_transcript(url):
    print(f"Fetching YouTube transcript for {url}...")
    try:
        video_id = None
        if "youtube.com/watch" in url:
            parsed_url = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed_url.query)
            if "v" in query:
                video_id = query["v"][0]
        elif "youtube.com/live/" in url:
            video_id = url.split("youtube.com/live/")[1].split("?")[0]
        elif "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0]
            
        if not video_id:
            print("Could not extract YouTube video ID.")
            return None
            
        channel = ""
        date = ""
        try:
            res = scraper.get(url, timeout=10)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                title_tag = soup.find("meta", property="og:title")
                if title_tag:
                    title = title_tag.get("content", "")
                else:
                    title = soup.title.text if soup.title else ""
                desc_tag = soup.find("meta", property="og:description") or soup.find("meta", name="description")
                if desc_tag:
                    description = desc_tag.get("content", "")
                    
                channel_tag = soup.find("link", itemprop="name")
                if channel_tag:
                    channel = channel_tag.get("content", "")
                    
                date_tag = soup.find("meta", itemprop="datePublished")
                if date_tag:
                    date = date_tag.get("content", "")
        except Exception as e:
            print(f"Could not fetch YouTube metadata: {e}")
            
        transcript_list = YouTubeTranscriptApi().list(video_id)
        transcript = None
        for t in transcript_list:
            transcript = t
            break
        
        if not transcript:
            raise Exception("No transcripts available for this video.")
            
        entries = transcript.fetch()
        lines = [entry.text.replace('\n', ' ') for entry in entries]
        paragraphs = []
        for i in range(0, len(lines), 10):
            paragraphs.append(" ".join(lines[i:i+10]))
        text = "\n\n".join(paragraphs)
        
        full_text = ""
        if title:
            full_text += f"# {title}\n\n"
        if description:
            full_text += f"{description}\n\n"
        full_text += f"## Transcript\n\n{text}"
        
        extracted_meta = {"contentUrl": url}
        if title: extracted_meta["name"] = title
        if description: extracted_meta["description"] = description
        if channel: extracted_meta["publisher"] = {"@type": "Organization", "name": channel}
        if date: extracted_meta["datePublished"] = date
        
        return full_text, extracted_meta
    except Exception as e:
        print(f"Failed to fetch YouTube transcript: {e}")
        return None, None

def extract_page_meta(soup, url):
    """Extract HTML-level metadata from a BeautifulSoup object.
    
    Returns a CreativeWork dict suitable for use in isBasedOn, containing
    title, description, keywords, author, og:/twitter: tags, canonical URL,
    and any structured JSON-LD found in <script type="application/ld+json">.
    """
    meta = {
        "@type": "CreativeWork",
        "name": "HTML Page Metadata",
        "url": url,
    }

    # <title>
    title_tag = soup.find('title')
    if title_tag and title_tag.string:
        meta["headline"] = title_tag.string.strip()

    # Collect all <meta> tags into a flat dict keyed by name/property
    meta_tags = {}
    for tag in soup.find_all('meta'):
        key = tag.get('name') or tag.get('property') or tag.get('http-equiv')
        content = tag.get('content', '').strip()
        if key and content:
            meta_tags[key.lower()] = content

    # Standard meta fields
    mapping = {
        'description':           'description',
        'keywords':              'keywords',
        'author':                'author',
        'robots':                'accessibilityHazard',   # closest schema.org field
        'og:title':              'alternativeHeadline',
        'og:description':        'abstract',
        'og:image':              'thumbnailUrl',
        'og:url':                'sameAs',
        'og:type':               'additionalType',
        'og:site_name':          'publisher',
        'article:published_time':'datePublished',
        'article:modified_time': 'dateModified',
        'article:author':        'creator',
        'twitter:title':         'alternateName',
        'twitter:description':   'disambiguatingDescription',
        'twitter:image':         'image',
        'twitter:site':          'accountablePerson',
    }
    for meta_key, schema_key in mapping.items():
        if meta_key in meta_tags and meta_tags[meta_key]:
            meta[schema_key] = meta_tags[meta_key]

    # <link rel="canonical">
    canonical = soup.find('link', rel='canonical')
    if canonical and canonical.get('href'):
        meta['canonicalUrl'] = canonical['href'].strip()

    # <link rel="alternate" hreflang="..."> language variants
    alternates = []
    for link in soup.find_all('link', rel='alternate'):
        hreflang = link.get('hreflang')
        href = link.get('href')
        if hreflang and href:
            alternates.append({'hreflang': hreflang, 'href': href})
    if alternates:
        meta['inLanguage'] = alternates

    # Embedded JSON-LD structured data
    ld_scripts = []
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            ld = json.loads(script.string or '')
            ld_scripts.append(ld)
        except Exception:
            pass
    if ld_scripts:
        meta['encodedIn'] = ld_scripts if len(ld_scripts) > 1 else ld_scripts[0]

    return meta

def fetch_github_repo(url, traverse=False):
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    path_parts = parsed.path.strip('/').split('/')
    if len(path_parts) >= 2:
        owner = path_parts[0]
        repo = path_parts[1]
        
        print(f"Fetching GitHub repository via API: {owner}/{repo}")
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md"
        
        try:
            repo_info = scraper.get(api_url, timeout=30).json()
            readme_res = scraper.get(readme_url, timeout=30)
            readme_content = readme_res.text if readme_res.status_code == 200 else "No README found."
            
            markdown_content = f"# {repo_info.get('name', repo)}\n\n"
            markdown_content += f"**Description:** {repo_info.get('description', '')}\n"
            markdown_content += f"**Stars:** {repo_info.get('stargazers_count', 0)}\n"
            markdown_content += f"**Forks:** {repo_info.get('forks_count', 0)}\n"
            markdown_content += f"**Language:** {repo_info.get('language', 'Unknown')}\n"
            markdown_content += f"**License:** {repo_info.get('license', {}).get('name', 'None') if repo_info.get('license') else 'None'}\n\n"
            markdown_content += f"## README\n\n{readme_content}"
            
            page_meta = {
                "@type": "SoftwareSourceCode",
                "name": repo_info.get("name", repo),
                "description": repo_info.get("description", ""),
                "url": url,
                "keywords": repo_info.get("topics", []),
                "github_stars": repo_info.get("stargazers_count", 0),
                "github_forks": repo_info.get("forks_count", 0)
            }
            
            return markdown_content, {"contentUrl": url}, [], page_meta
            
        except Exception as e:
            print(f"Failed to fetch GitHub API for {url}: {e}")
            
    return None

def fetch_url_markdown(url, traverse=False):
    if "github.com" in url and "api.github.com" not in url:
        parsed = urllib.parse.urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) == 2:
            res = fetch_github_repo(url, traverse)
            if res:
                return res
                
    if "youtube.com" in url or "youtu.be" in url:
        yt_text, yt_meta = fetch_youtube_transcript(url)
        if traverse:
            return yt_text, yt_meta, []
        return yt_text, yt_meta
        
    print(f"Fetching {url}...")
    try:
        if os.path.exists(url):
            is_local = True
            with open(url, "rb") as f:
                content_bytes = f.read()
            import mimetypes
            content_type = mimetypes.guess_type(url)[0] or ""
            is_pdf = url.lower().endswith('.pdf') or 'application/pdf' in content_type
        else:
            is_local = False
            response = scraper.get(url, timeout=30)
            content_bytes = response.content
            content_type = response.headers.get('content-type', '').lower()
            is_pdf = 'application/pdf' in content_type or url.lower().endswith('.pdf')
            
        if is_pdf:
            try:
                from pypdf import PdfReader
                import io
                
                import hashlib
                from datetime import datetime, timezone

                pdf_bytes = content_bytes
                checksum = hashlib.sha256(pdf_bytes).hexdigest()
                size = len(pdf_bytes)
                
                print("Detected PDF document. Extracting text...")
                pdf_file = io.BytesIO(pdf_bytes)
                reader = PdfReader(pdf_file)
                text = ""
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n\n"
                    
                meta = {
                    "name": url.split('/')[-1] or "PDF Document",
                    "contentUrl": url,
                    "encodingFormat": "application/pdf",
                    "contentSize": f"{size} B",
                    "sha256": checksum,
                    "retrievalTimestamp": datetime.now(timezone.utc).isoformat(),
                }
                if not is_local:
                    meta["httpHeaders"] = dict(response.headers)
                    if response.headers.get('Last-Modified'):
                        meta["dateModified"] = response.headers.get('Last-Modified')
                    if response.headers.get('ETag'):
                        meta["version"] = response.headers.get('ETag').strip('"')
                
                if traverse:
                    return text.strip(), meta, []
                return text.strip(), meta
            except Exception as e:
                print(f"Failed to parse PDF: {e}")

        if is_local:
            try:
                html_text = content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                html_text = content_bytes.decode('latin-1')
        else:
            html_text = response.text
            if ("JavaScript is disabled" in html_text and "verify that you're not a robot" in html_text) or response.status_code in (202, 403):
                print("Detected bot protection challenge in response. Triggering Playwright fallback...")
                pw_content = fetch_with_playwright(url)
                if pw_content:
                    html_text = pw_content
            else:
                response.raise_for_status()

        # If local and not HTML, return as raw text directly
        if is_local and not (html_text.strip().lower().startswith('<!doctype html') or '<html' in html_text.lower() or '<body' in html_text.lower()):
            page_meta = {
                "@type": "CreativeWork",
                "name": url.split('/')[-1] or "Local Document",
                "url": url,
            }
            if traverse:
                return html_text.strip(), {"contentUrl": url}, [], page_meta
            else:
                return html_text.strip(), {"contentUrl": url}

        soup = BeautifulSoup(html_text, 'html.parser')

        # Extract HTML-level metadata (title, meta tags, JSON-LD, etc.)
        page_meta = extract_page_meta(soup, url)

        parsed_base = urllib.parse.urlparse(url)
        base_path = parsed_base.path
        if traverse:
            if not base_path.endswith('/'):
                base_path = base_path[:base_path.rfind('/')+1]
        else:
            if not base_path.endswith('/'):
                base_path += '/'
            
        # Find all subpage links (e.g. /library/model/tags)
        sub_links = {}
        for a in soup.find_all('a', href=True):
            href = a['href']
            # If it's a relative link that starts with the base path
            if href.startswith(base_path) and href != base_path and href not in sub_links:
                link_text = a.get_text(strip=True)
                if not link_text:
                    link_text = href.split('/')[-1]
                sub_links[href] = link_text
                
        # Try to find the entry-content (WordPress), article, main content, otherwise use body
        content = soup.find(class_='entry-content') or soup.find('article') or soup.find('main') or soup.find('body')
        if content:
            # Strip out noisy structural elements (header, footer, nav, sidebar)
            for element in content.find_all(['header', 'footer', 'nav', 'aside']):
                element.decompose()
            # Strip out common WordPress garbage classes
            for element in content.find_all(class_=['widget', 'nv-sidebar-wrap', 'nv-post-navigation', 'sharedaddy', 'jp-relatedposts', 'post-navigation', 'related-posts']):
                element.decompose()
                
            html_str = str(content)
            for tag in ['</span>', '</div>', '</li>', '</td>', '</th>', '</a>']:
                html_str = html_str.replace(tag, tag + ' ')
            md = markdownify.markdownify(html_str, heading_style="ATX").strip()
            
            # Clean up common WordPress injected footers from the markdown
            for noise_marker in ["### Related Posts", "Continue Reading", "### Share this:"]:
                if noise_marker in md:
                    md = md.split(noise_marker)[0].strip()
            markdown_content = md
            
            # Fetch subpages
            sibling_pages = []
            if traverse:
                for sub_link, link_text in sub_links.items():
                    sub_url = urllib.parse.urljoin(url, sub_link)
                    print(f"  -> Fetching sibling page {sub_url}...")
                    try:
                        sub_res = scraper.get(sub_url, timeout=30)
                        if sub_res.status_code == 200:
                            sub_soup = BeautifulSoup(sub_res.text, 'html.parser')
                            sub_title = link_text
                            sub_content = sub_soup.find(class_='entry-content') or sub_soup.find('article') or sub_soup.find('main') or sub_soup.find('body')
                            if sub_content:
                                for element in sub_content.find_all(['header', 'footer', 'nav', 'aside']):
                                    element.decompose()
                                for element in sub_content.find_all(class_=['widget', 'nv-sidebar-wrap', 'nv-post-navigation', 'sharedaddy', 'jp-relatedposts', 'post-navigation', 'related-posts']):
                                    element.decompose()
                                sub_html_str = str(sub_content)
                                for tag in ['</span>', '</div>', '</li>', '</td>', '</th>', '</a>']:
                                    sub_html_str = sub_html_str.replace(tag, tag + ' ')
                                sub_md = markdownify.markdownify(sub_html_str, heading_style="ATX").strip()
                                for noise_marker in ["### Related Posts", "Continue Reading", "### Share this:"]:
                                    if noise_marker in sub_md:
                                        sub_md = sub_md.split(noise_marker)[0].strip()
                                sibling_pages.append({'url': sub_url, 'title': sub_title.strip() if isinstance(sub_title, str) else str(sub_title), 'markdown': sub_md})
                    except Exception as e:
                        print(f"  -> Failed to fetch subpage {sub_url}: {e}")
            else:
                for sub_link in sub_links.keys():
                    sub_url = urllib.parse.urljoin(url, sub_link)
                    print(f"  -> Fetching subpage {sub_url}...")
                    try:
                        sub_res = scraper.get(sub_url, timeout=30)
                        if sub_res.status_code == 200:
                            sub_soup = BeautifulSoup(sub_res.text, 'html.parser')
                            sub_content = sub_soup.find(class_='entry-content') or sub_soup.find('article') or sub_soup.find('main') or sub_soup.find('body')
                            if sub_content:
                                for element in sub_content.find_all(['header', 'footer', 'nav', 'aside']):
                                    element.decompose()
                                for element in sub_content.find_all(class_=['widget', 'nv-sidebar-wrap', 'nv-post-navigation', 'sharedaddy', 'jp-relatedposts', 'post-navigation', 'related-posts']):
                                    element.decompose()
                                sub_html_str = str(sub_content)
                                for tag in ['</span>', '</div>', '</li>', '</td>', '</th>', '</a>']:
                                    sub_html_str = sub_html_str.replace(tag, tag + ' ')
                                sub_md = markdownify.markdownify(sub_html_str, heading_style="ATX").strip()
                                for noise_marker in ["### Related Posts", "Continue Reading", "### Share this:"]:
                                    if noise_marker in sub_md:
                                        sub_md = sub_md.split(noise_marker)[0].strip()
                                markdown_content += f"\n\n--- Content from {sub_url} ---\n\n{sub_md}"
                    except Exception as e:
                        print(f"  -> Failed to fetch subpage {sub_url}: {e}")
                    
            return markdown_content, {"contentUrl": url}, sibling_pages, page_meta
        else:
            print("No main or body content could be extracted.")
            return None, None, [], None
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        try:
            print(f"Attempting fallback to Jina Reader API for {url}...")
            jina_url = f"https://r.jina.ai/{url}"
            fallback_res = requests.get(jina_url, timeout=60)
            fallback_res.raise_for_status()
            return fallback_res.text, {"contentUrl": url}, []
        except Exception as jina_e:
            print(f"Jina Reader fallback also failed: {jina_e}")
            return None, None, []

def translate_to_english(text):
    print("Translating content to English using Ollama...")
    prompt = f"Translate the ENTIRE following text to English. Do not summarize. Translate every single word until the end of the text:\n\n{text}"
    ollama_host = os.environ.get("OLLAMA_HOST", "http://10.147.18.82:11435")
    payload = {
        "model": "qwen3.5:27b",
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 4096
        }
    }
    print(f"DEBUG: Payload sent to Ollama: {repr(payload)}")
    try:
        res = requests.post(f"{ollama_host}/api/generate", json=payload, timeout=600)
        if res.status_code == 200:
            translated = res.json().get('response', '').strip()
            print(f"DEBUG: Translated response from Ollama: {repr(translated[:100])}")
            return translated
        else:
            print(f"Error {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Translation failed: {e}")
    print(f"DEBUG: Falling back to returning original text")
    return text

def get_elasticsearch_version(url, expert="/croissant"):
    try:
        import hashlib
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        es_url = ELASTICSEARCH_URL.rstrip('/')
        
        # Extract index name from expert path (e.g., /expert/honduras -> honduras)
        index_name = expert.strip('/').split('/')[-1]
        if not index_name:
            index_name = "croissant"
            
        resp = requests.get(f"{es_url}/{index_name}/_doc/{url_hash}", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            source = data.get("_source", {})
            version_str = source.get("version", "0.0")
            try:
                # Increment the minor version (e.g., 1.0 -> 1.1)
                major, minor = version_str.split('.')
                return f"{major}.{int(minor) + 1}"
            except Exception:
                return "1.1" # Fallback if not a simple decimal
    except Exception as e:
        print(f"Warning: Failed to check ES version: {e}")
    return None

def convert_oai_to_croissant(doc):
    croissant = {
        "@context": {
            "@language": "en",
            "@vocab": "https://schema.org/",
            "cr": "http://mlcommons.org/croissant/",
            "sc": "https://schema.org/",
            "dct": "http://purl.org/dc/terms/"
        },
        "@type": "sc:Dataset",
        "conformsTo": "http://mlcommons.org/croissant/1.0",
        "name": "Unknown Dataset",
        "description": "No description provided.",
        "url": ""
    }
    if not isinstance(doc, dict): return None
    metadata = doc.get("ore:describes", doc)
    
    if "title" in metadata: croissant["name"] = metadata["title"]
    elif "schema:name" in metadata: croissant["name"] = metadata["schema:name"]
    elif "name" in metadata: croissant["name"] = metadata["name"]
    
    # Handle Dataverse specific description field
    if "citation:dsDescription" in metadata:
        desc_obj = metadata["citation:dsDescription"]
        if isinstance(desc_obj, list) and len(desc_obj) > 0:
            if "citation:dsDescriptionValue" in desc_obj[0]:
                croissant["description"] = desc_obj[0]["citation:dsDescriptionValue"]
    elif "dsDescription" in metadata:
        desc_obj = metadata["dsDescription"]
        if isinstance(desc_obj, list) and len(desc_obj) > 0:
            if "dsDescriptionValue" in desc_obj[0]:
                croissant["description"] = desc_obj[0]["dsDescriptionValue"]
    elif "schema:description" in metadata: croissant["description"] = metadata["schema:description"]
    elif "description" in metadata: croissant["description"] = metadata["description"]
    
    if "url" in metadata: croissant["url"] = metadata["url"]
    elif "@id" in metadata: croissant["url"] = metadata["@id"]
    elif "@id" in doc: croissant["url"] = doc["@id"]
    return croissant

def index_into_elasticsearch(url, json_data, markdown_data, expert="/croissant"):
    # Extract index name from expert path (e.g., /expert/honduras -> honduras)
    index_name = expert.strip('/').split('/')[-1]
    if not index_name:
        index_name = "croissant"
        
    print(f"\n--- Indexing into Elasticsearch (index: {index_name}) ---")
    try:
        import hashlib
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        es_url = ELASTICSEARCH_URL.rstrip('/')

        # Ensure index exists with full-text mapping
        idx_check = requests.head(f"{es_url}/{index_name}", timeout=5)
        if idx_check.status_code == 404:
            mapping = {
                "settings": {
                    "index.mapping.total_fields.limit": 20000
                },
                "mappings": {
                    "date_detection": False,
                    "properties": {
                        "_full_text":      {"type": "text", "analyzer": "english"},
                        "_markdown_text":  {"type": "text", "analyzer": "english"},
                        "_source_url":     {"type": "keyword"},
                        "@context":        {"type": "object", "enabled": False},
                        "@type":           {"type": "keyword"},
                        "name":            {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                        "description":     {"type": "text", "analyzer": "english"},
                        "keywords":        {"type": "keyword"},
                        "contentUrl":      {"type": "keyword"},
                        "url":             {"type": "keyword"},
                        "conformsTo":      {"type": "keyword"},
                        "datePublished":   {"type": "date", "ignore_malformed": True},
                        "license":         {"type": "keyword"},
                        "author":          {"type": "flattened"},
                        "publisher":       {"type": "flattened"},
                        "creator": {
                            "properties": {
                                "@type":   {"type": "keyword"},
                                "name":    {"type": "text"},
                                "email":   {"type": "keyword"}
                            }
                        },
                        "distribution": {
                            "type": "nested",
                            "properties": {
                                "@type":           {"type": "keyword"},
                                "name":            {"type": "text"},
                                "description":     {"type": "text", "analyzer": "english"},
                                "contentUrl":      {"type": "keyword"},
                                "encodingFormat":  {"type": "keyword"}
                            }
                        },
                        "isBasedOn": {
                            "type": "nested",
                            "properties": {
                                "@type":           {"type": "keyword"},
                                "name":            {"type": "text"},
                                "url":             {"type": "keyword"},
                                "contentUrl":      {"type": "keyword"},
                                "encodingFormat":  {"type": "keyword"},
                                "headline":        {"type": "text"},
                                "description":     {"type": "text", "analyzer": "english"},
                                "alternativeHeadline": {"type": "text"},
                                "abstract":        {"type": "text", "analyzer": "english"},
                                "encodedIn":       {"type": "flattened"}
                            }
                        },
                        "cr_recordSet": {
                            "type": "nested",
                            "properties": {
                                "@type":           {"type": "keyword"},
                                "@id":             {"type": "keyword"},
                                "name":            {"type": "text"},
                                "description":     {"type": "text", "analyzer": "english"}
                            }
                        },
                        "unmappedFields": {
                            "type": "nested",
                            "properties": {
                                "@type":  {"type": "keyword"},
                                "value":  {"type": "text"}
                            }
                        }
                    }
                }
            }
            requests.put(f"{es_url}/{index_name}", json=mapping,
                         headers={"Content-Type": "application/json"}, timeout=10)
            print(f"  Created '{index_name}' index with comprehensive Croissant schema mapping.")

        # Collect all string leaf values from the JSON-LD for full-text search
        def collect_text(obj):
            parts = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if not k.startswith('@'):
                        parts.extend(collect_text(v))
            elif isinstance(obj, list):
                for item in obj:
                    parts.extend(collect_text(item))
            elif isinstance(obj, str) and obj.strip():
                parts.append(obj.strip())
            return parts

        full_text_parts = collect_text(json_data)

        def normalize_jsonld(obj):
            if isinstance(obj, dict):
                if "@value" in obj and len(obj) <= 2:
                    return obj["@value"]
                return {k: normalize_jsonld(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [normalize_jsonld(x) for x in obj]
            return obj

        es_doc = normalize_jsonld(json_data)
        es_doc['_source_url']    = url
        es_doc['_markdown_text'] = markdown_data or ''          # full markdown
        es_doc['_full_text']     = '\n'.join(full_text_parts)   # all JSON-LD text values

        resp = requests.put(
            f"{es_url}/{index_name}/_doc/{url_hash}",
            json=es_doc,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        if resp.status_code in (200, 201):
            chars = len(es_doc['_markdown_text'])
            print(f"✓ Successfully indexed into Elasticsearch! "
                  f"(result: {resp.json().get('result', '?')}, "
                  f"markdown: {chars} chars, text fields: {len(full_text_parts)})")
        else:
            print(f"✗ Elasticsearch returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"✗ Failed to index into Elasticsearch: {e}")

def check_dataverse_direct_export(url):
    try:
        if "doi.org" in url:
            res = requests.head(url, allow_redirects=True, timeout=10)
            target_url = res.url
        else:
            target_url = url
            
        if "persistentId=doi:" in target_url:
            parsed = urllib.parse.urlparse(target_url)
            query = urllib.parse.parse_qs(parsed.query)
            persistent_id = query.get("persistentId", [""])[0]
            if persistent_id:
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                
                for exporter in ["croissant", "schema.org"]:
                    export_url = f"{base_url}/api/datasets/export?exporter={exporter}&persistentId={persistent_id}"
                    print(f"Dataverse URL detected. Trying direct export from {export_url}")
                    res = requests.get(export_url, timeout=15)
                    
                    if res.status_code == 200:
                        if 'json' in res.headers.get('content-type', '').lower():
                            try:
                                data = res.json()
                                if data.get("status") != "ERROR":
                                    return data
                            except json.JSONDecodeError:
                                pass
                        else:
                            print("Direct export returned non-JSON. Trying Playwright...")
                            pw_content = fetch_with_playwright(export_url)
                            if pw_content:
                                try:
                                    soup = BeautifulSoup(pw_content, 'html.parser')
                                    data = json.loads(soup.body.text)
                                    if data.get("status") != "ERROR":
                                        return data
                                except Exception:
                                    pass
                    elif res.status_code in (202, 403) and 'html' in res.headers.get('content-type', '').lower():
                        print("Direct export intercepted by WAF. Trying Playwright...")
                        pw_content = fetch_with_playwright(export_url)
                        if pw_content:
                            try:
                                soup = BeautifulSoup(pw_content, 'html.parser')
                                data = json.loads(soup.body.text)
                                if data.get("status") != "ERROR":
                                    return data
                            except Exception:
                                pass
    except Exception as e:
        print(f"Direct export check failed: {e}")
    return None

def convert_to_croissant(url, is_slice=False, traverse=False, reingest=False, user_name=None, user_email=None, index=False, elastic=False, expert="/expert/croissant", upload_gdrive=False, upload_gdrive_folder=None):
    direct_jsonld = check_dataverse_direct_export(url)
    if direct_jsonld:
        print("✓ Successfully retrieved Croissant JSON-LD directly from Dataverse API!")
        json_data = direct_jsonld
        
        # Check Elasticsearch for existing version and increment if necessary
        if "version" not in json_data:
            json_data["version"] = "1.0"
        es_version = get_elasticsearch_version(url, expert)
        if es_version:
            json_data["version"] = str(es_version)
            print(f"  ✓ Resource already in Elasticsearch. Updating version to {es_version}")
            
        if expert:
            if "isPartOf" not in json_data:
                json_data["isPartOf"] = []
            elif not isinstance(json_data["isPartOf"], list):
                json_data["isPartOf"] = [json_data["isPartOf"]]
            json_data["isPartOf"].append({"@type": "Collection", "name": expert})
            
        output = json.dumps(json_data, indent=2)
        
        parsed_url = urllib.parse.urlparse(url)
        safe_name = parsed_url.netloc + parsed_url.path
        safe_name = safe_name.replace("/", "_").replace(".", "_")
        if parsed_url.query:
            qs = urllib.parse.parse_qsl(parsed_url.query)
            for k, v in qs:
                safe_name += "_" + v
        import re
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', safe_name)
        if not safe_name:
            safe_name = "url_output"
            
        os.makedirs(os.path.join("data", "ca4eosc"), exist_ok=True)
        safe_name = os.path.join("data", "ca4eosc", safe_name)
        output_filename = f"{safe_name}_croissant.jsonld"
        
        with open(output_filename, "w", encoding='utf-8') as f:
            f.write(output)
        print(f"\nOutput saved to {output_filename}")
        
        md_filename = f"{safe_name}_content.md"
        title = json_data.get("name", "Dataverse Dataset")
        desc = json_data.get("description", "No description provided.")
        if isinstance(desc, list): desc = " ".join(desc)
        md_content = f"# {title}\n\n**Description:** {desc}\n\n"
        if "keywords" in json_data:
            kw = json_data["keywords"]
            md_content += f"**Keywords:** {', '.join(kw) if isinstance(kw, list) else kw}\n\n"
            
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"Extracted markdown saved to {md_filename}")

        try:
            from langdetect import detect
            lang = detect(md_content)
            print(f"Detected language: {lang}")
        except Exception as e:
            lang = "unknown"

        if lang != "en":
            print(f"DEBUG: Translating desc of length {len(desc)}: {repr(desc[:100])}")
            translated_desc = translate_to_english(desc)
            if translated_desc and translated_desc != desc:
                json_data["description"] = translated_desc
                
                # Reconstruct english markdown
                translated_md = f"# {title}\n\n**Description:** {translated_desc}\n\n"
                if "keywords" in json_data:
                    kw = json_data["keywords"]
                    translated_md += f"**Keywords:** {', '.join(kw) if isinstance(kw, list) else kw}\n\n"
                
                md_content = translated_md
                md_filename = f"{safe_name}_en_content.md"
                with open(md_filename, "w", encoding='utf-8') as f:
                    f.write(md_content)
                print(f"Extracted markdown saved to {md_filename}") # Keep exact format for agent script extraction
                
                # Add translationOfWork provenance
                if "creator" not in json_data:
                    json_data["creator"] = []
                elif not isinstance(json_data["creator"], list):
                    json_data["creator"] = [json_data["creator"]]
                
                json_data["creator"].append({
                    "@type": "SoftwareApplication",
                    "name": "qwen3.5:27b",
                    "description": "Translation generated by AI model"
                })
                json_data["translationOfWork"] = {
                    "@id": url
                }
                
                # Re-save the JSON-LD with the updated provenance and description
                output = json.dumps(json_data, indent=2)
                with open(output_filename, "w", encoding='utf-8') as f:
                    f.write(output)

        if reingest:
            print("\n--- Ingesting into QLever ---")
            try:
                api_base = os.environ.get("API_BASE", "http://localhost:7013")
                res_ql = requests.post(f"{api_base}/add_record", json=json_data, timeout=10)
                res_ql.raise_for_status()
                print(f"✓ Successfully ingested into QLever! Response: {res_ql.text}")
            except Exception as e:
                print(f"✗ Failed to ingest into QLever: {e}")
                
        if elastic:
            index_into_elasticsearch(url, json_data, "", expert)
            
        if upload_gdrive and user_email:
            print(f"Skipping Google Drive upload for direct Dataverse export because no Markdown content was generated (only Croissant metadata is available).")
        return

    page_meta = None
    sibling_pages = []
    
    result = fetch_url_markdown(url, traverse)
    if len(result) == 4:
        markdown_data, extracted_meta, sibling_pages, page_meta = result
    elif len(result) == 3:
        markdown_data, extracted_meta, sibling_pages = result
    else:
        markdown_data, extracted_meta = result


    if not markdown_data:
        print("Error: Could not extract markdown.")
        return

    # Generate a safe filename based on the URL
    parsed_url = urllib.parse.urlparse(url)
    safe_name = parsed_url.netloc + parsed_url.path
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', safe_name)
    if not safe_name:
        safe_name = "url_output"
        
    os.makedirs(os.path.join("data", "ca4eosc"), exist_ok=True)
    safe_name = os.path.join("data", "ca4eosc", safe_name)

    md_filename = f"{safe_name}_content.md"
    croissant_filename = os.path.basename(f"{safe_name}_croissant.jsonld")
    header = f"# Document: {url}\n\n* **Croissant Metadata**: [{croissant_filename}](./{croissant_filename})\n\n"
    
    # Don't duplicate if already present
    if not markdown_data.startswith(f"# Document: {url}"):
        markdown_data = header + markdown_data
        
    with open(md_filename, "w", encoding='utf-8') as f:
        f.write(markdown_data)
        
    print(f"Extracted markdown saved to {md_filename}")
    
    # Upload to Vault if MinIO is configured
    try:
        minio_url = os.environ.get("MINIO_URL", "http://minio:9000")
        minio_user = os.environ.get("MINIO_ROOT_USER", "minioadmin")
        minio_pass = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin")
        if minio_url:
            from minio import Minio
            endpoint = minio_url.replace("http://", "").replace("https://", "")
            client = Minio(
                endpoint,
                access_key=minio_user,
                secret_key=minio_pass,
                secure=minio_url.startswith("https")
            )
            # Ensure vault bucket exists
            if not client.bucket_exists("vault"):
                client.make_bucket("vault")
            
            vault_filename = os.path.basename(md_filename)
            md_bytes = markdown_data.encode('utf-8')
            client.put_object(
                "vault",
                vault_filename,
                data=io.BytesIO(md_bytes),
                length=len(md_bytes),
                content_type="text/markdown"
            )
            print(f"Extracted markdown successfully uploaded to vault: https://mcp.dev.codata.org/vault/{vault_filename}")
    except Exception as e:
        print(f"Warning: Failed to upload markdown to MinIO vault: {e}")

    try:
        from langdetect import detect
        lang = detect(markdown_data)
        print(f"Detected language: {lang}")
    except Exception as e:
        print(f"Language detection failed: {e}")

    original_md_filename = md_filename
    if lang != "en":
        translated_md = translate_to_english(markdown_data)
        if translated_md and translated_md != markdown_data:
            markdown_data = translated_md
            md_filename = f"{safe_name}_en_content.md"
            with open(md_filename, "w", encoding='utf-8') as f:
                f.write(markdown_data)
            print(f"Translated markdown saved to {md_filename}")
            try:
                import io
                vault_en_filename = os.path.basename(md_filename)
                en_bytes = markdown_data.encode('utf-8')
                client.put_object(
                    "vault",
                    vault_en_filename,
                    data=io.BytesIO(en_bytes),
                    length=len(en_bytes),
                    content_type="text/markdown"
                )
                print(f"Translated markdown successfully uploaded to vault: https://mcp.dev.codata.org/vault/{vault_en_filename}")
            except Exception as e:
                print(f"Warning: Failed to upload translated markdown to MinIO vault: {e}")

    slice_links = []
    if is_slice:
        print(f"\n--- Slicing Markdown into readable pieces ---")
        paragraphs = markdown_data.split('\n\n')
        chunks = []
        current_chunk = ""
        for p in paragraphs:
            # Chunking to roughly ~3000 characters to keep pieces readable and fast to process
            if len(current_chunk) + len(p) > 3000 and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = p
            else:
                current_chunk += "\n\n" + p
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        print(f"Document split into {len(chunks)} pieces.")
        for i, chunk in enumerate(chunks, 1):
            parsed_json = {}
            part_filename = f"{safe_name}_part_{i}.md"
            with open(part_filename, "w", encoding='utf-8') as f:
                f.write(chunk)
            
            print(f"Generating metadata for Part {i}...")
            
            # 1. Extract Title from markdown heading
            title = ""
            import re
            match = re.search(r'^(#{1,6})\s+(.+)$', chunk, re.MULTILINE)
            if match:
                title = match.group(2).strip()
            
            # Single LLM pass for remaining chunk metadata
            chunk_prompt = (
                "Please analyze the following text and extract three things into a JSON object.\n"
                "Output ONLY a valid JSON object matching this exact structure:\n"
                "{\n"
                '  "summary": "A 1-sentence summary",\n'
                '  "topics": "- Topic 1\\n- Topic 2",\n'
                '  "keywords": ["Entity1", "Entity2"]\n'
                "}\n\n"
                "For keywords, specifically extract ALL named entities (people, organizations, locations, concepts) relevant to the segment. Do NOT limit the number of keywords; list as many as you can find in the text.\n"
                f"Text:\n\n{chunk[:4000]}\n"
            )
            payload_chunk = {
                "model": "gemma4:e2b",
                "prompt": chunk_prompt,
                "stream": False,
                "options": { "temperature": 0.5, "num_predict": 256 }
            }
            try:
                res_chunk = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload_chunk, timeout=600)
                res_chunk.raise_for_status()
                response_text = res_chunk.json().get('response', '').strip()
                
                # Extract JSON from markdown code block if present
                import re
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)
                elif response_text.startswith('{') and response_text.endswith('}'):
                    pass
                else:
                    # Try to extract the first { to the last }
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        response_text = json_match.group(0)
                        
                if not response_text:
                    response_text = '{}'
                parsed_json = json.loads(response_text)
                
                summary = parsed_json.get("summary", parsed_json.get("description", "")).strip()
                
                # Check topics, or fallback to keywords or text if gemma uses different keys
                raw_topics = parsed_json.get("topics", parsed_json.get("keywords", parsed_json.get("text", "")))
                if isinstance(raw_topics, list):
                    topics = "\n".join(f"- {t}" for t in raw_topics)
                else:
                    topics = str(raw_topics).strip()
                    
                keywords_list = parsed_json.get("keywords", [])
                if not isinstance(keywords_list, list):
                    keywords_list = []
            except Exception as e:
                print(f"Failed to extract metadata for Part {i}: {e}")
                summary, topics, keywords_list = "", "", []
                
            if not title:
                title = f"Document Part {i}"
            if not summary:
                _out = parsed_json if 'parsed_json' in locals() else None
                print(f"⚠ Warning: Could not find summary in chunk {i}. LLM Output: {_out}")
                summary = f"Segment of content from {url}"
            if not topics:
                topics = f"- Extracted content from {url}"
                
            abs_path = os.path.abspath(part_filename)
            
            slice_data = {
                "@type": "CreativeWork",
                "name": title,
                "position": i,
                "description": summary,
                "text": topics,
                "keywords": keywords_list,
                "contentUrl": f"file://{abs_path}",
                "encodingFormat": "text/markdown"
            }
            
            if i > 1:
                slice_data["previousItem"] = i - 1
            if i < len(chunks):
                slice_data["nextItem"] = i + 1
                
            slice_links.append(slice_data)
            print(f"Saved and summarized {part_filename}")
            
            # Send dry-run ingestion request to Ollama
            ingest_prompt = (
                f"Please process and mentally store the following document chunk. "
                f"Source URL: {url}\n"
                f"Title: {title}\n"
                f"Summary: {summary}\n"
                f"Topics: {topics}\n"
                f"Keywords: {', '.join(keywords_list)}\n\n"
                f"Content:\n{chunk}\n\n"
                "Acknowledge that you have processed this chunk by replying 'ACKNOWLEDGED'."
            )
            ingest_payload = {
                "model": "gemma4:e2b",
                "prompt": ingest_prompt,
                "stream": False,
                "options": { "temperature": 0.0 }
            }
            try:
                print(f"Sending chunk {i} to Ollama for dry-run ingestion...")
                res_ingest = requests.post(f"{OLLAMA_HOST}/api/generate", json=ingest_payload, timeout=120)
                res_ingest.raise_for_status()
                print(f"Ollama ingestion response: {res_ingest.json().get('response', '').strip()}")
            except Exception as e:
                print(f"Failed to send chunk {i} to Ollama: {e}")

    print(f"\n--- Processing {url} using {MODEL_NAME} ---")
    
    # Truncate to first 5,000 characters to prevent context window overflow which causes hallucinated JSON
    llm_context_data = markdown_data
    if len(llm_context_data) > 5000:
        print(f"Warning: Markdown is too large ({len(llm_context_data)} chars). Truncating to 5,000 chars.")
        llm_context_data = llm_context_data[:5000]

    prompt = f"Create Croissant JSON-LD metadata for a machine learning model or dataset. The source URL is {url}."
    if lang != 'en':
        prompt += f" The source documentation is in language code '{lang}'. Please do a precise ONE-to-ONE translation of the relevant metadata to English and output the Croissant JSON-LD entirely in English."
    prompt += f" Here is the documentation and description extracted from its official page:\n\n{llm_context_data}\n\n"
    prompt += "Extract relevant information such as the description, authors, license, keywords, tags, or any dataset dependencies into the Croissant metadata if available. Map keywords/tags to the standard schema:keywords property, and extract them EXACTLY as they appear in the text (do not change casing or invent new tags). Ensure 'keywords' is formatted as a JSON array of strings, not a single comma-separated string. IMPORTANT: For any fields or data that do not have a standard mapping in Croissant, include them in the JSON-LD under a custom field called 'unmappedFields' as a list of key-value pairs.\n"
    prompt += "CRITICAL: You MUST use the exact following JSON-LD structure and include ALL of these top-level fields: '@context', '@type', 'name', 'description', 'url', 'license', 'keywords', 'unmappedFields', 'contentUrl', 'isBasedOn', 'isPartOf', 'version', 'creator'.\n"
    prompt += 'Example structure:\n{\n  "@context": {\n    "@language": "en",\n    "@vocab": "https://schema.org/",\n    "cr": "http://mlcommons.org/croissant/",\n    "dct": "http://purl.org/dc/terms/",\n    "sc": "https://schema.org/",\n    "conformsTo": "dct:conformsTo",\n    "distribution": {"@id": "cr:distribution"},\n    "bs4ExtractionPattern": {"@id": "sc:processingRequirement", "@type": "@json"},\n    "unf": "https://guides.dataverse.org/en/6.9/developers/unf/unf-v6.html",\n    "odrl": "http://www.w3.org/ns/odrl/2/",\n    "cdif": "https://cdif.org/1.1/",\n    "did": "https://www.w3.org/ns/did/v1"\n  },\n  "@type": "sc:SoftwareApplication",\n  "name": "...",\n  "description": "...",\n  "url": "...",\n  "license": "...",\n  "keywords": [],\n  "unmappedFields": [],\n  "contentUrl": "...",\n  "isBasedOn": [],\n  "isPartOf": [{"@type": "Collection", "name": "/expert/croissant"}],\n  "version": "1.0",\n  "creator": {"@type": "Person", "name": "...", "email": "..."}\n}\n\n'
    prompt += "CRITICAL: Do NOT invent, hallucinate, or generate generic information. You MUST extract the name, description, and details directly from the provided text above.\n\nOutput ONLY a valid JSON object."
    
    start_time = time.time()
    try:
        MAX_RETRIES = 3
        for attempt in range(1, MAX_RETRIES + 1):
            # Increase temperature on retries to avoid repeating the exact same JSON syntax errors
            current_temperature = 0.1 + ((attempt - 1) * 0.2)
            # Inject attempt number into prompt to bypass Ollama cache
            current_prompt = prompt
            if attempt > 1:
                current_prompt += f"\n\n[Attempt {attempt} - Previous attempt failed due to invalid JSON. Please ensure valid JSON formatting, avoid truncation, and do not repeat previous errors.]"
                
            payload = {
                "model": MODEL_NAME,
                "prompt": current_prompt,
                "stream": False,
                "options": {
                    "temperature": current_temperature,
                    "repeat_penalty": 1.1,
                    "num_predict": 8192,
                    "num_ctx": 40960
                }
            }
            
            response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=600)
            response.raise_for_status()
            end_time = time.time()
            
            data = response.json()
            print(f"Status: Success (Attempt {attempt})")
            print(f"Total Request Time: {end_time - start_time:.2f} s")
            print(f"Prompt Eval Tokens: {data.get('prompt_eval_count')} in {data.get('prompt_eval_duration', 0) / 1e9:.2f} s")
            print(f"Tokens Generated: {data.get('eval_count')} in {data.get('eval_duration', 0) / 1e9:.2f} s")
            if data.get('eval_duration', 0) > 0:
                speed = data.get('eval_count', 0) / (data.get('eval_duration', 0) / 1e9)
                print(f"Generation Speed: {speed:.2f} tokens/sec")
            print("-" * 40)
            
            output = data.get('response', '')
            
            # Strip markdown formatting
            if output.startswith("```json"):
                output = output[7:]
            if output.startswith("```"):
                output = output[3:]
            if output.endswith("```"):
                output = output[:-3]
            output = output.strip()
            
            # Validation
            if attempt > 1:
                print(f"\n--- Validation (Attempt {attempt}) ---")
            else:
                print("\n--- Validation ---")
                
            try:
                # Clean up common LLM trailing commas before parsing
                import re
                output = re.sub(r',\s*}', '}', output)
                output = re.sub(r',\s*\]', ']', output)
                
                json_data = json.loads(output)
                print("✓ JSON is well-formed")
                
                # Inject link to the generated markdown file(s)
                original_vault_url = f"https://mcp.dev.codata.org/vault/{os.path.basename(original_md_filename)}"
                doc_links = [{
                    "@type": "CreativeWork",
                    "name": "Scraped Markdown Content",
                    "contentUrl": original_vault_url,
                    "encodingFormat": "text/markdown"
                }]
                
                if original_md_filename != md_filename:
                    translated_vault_url = f"https://mcp.dev.codata.org/vault/{os.path.basename(md_filename)}"
                    doc_links.append({
                        "@type": "CreativeWork",
                        "name": "Translated Markdown Content (English)",
                        "contentUrl": translated_vault_url,
                        "encodingFormat": "text/markdown",
                        "creator": {
                            "@type": "SoftwareApplication",
                            "name": MODEL_NAME,
                            "description": "Translation generated by AI model"
                        },
                        "translationOfWork": {
                            "@id": original_vault_url
                        }
                    })
                    
                if traverse and sibling_pages:
                    for sib in sibling_pages:
                        sib_safe = re.sub(r'[^a-zA-Z0-9]', '_', sib['url']).strip('_')
                        sib_md_filename = os.path.join("data", "ca4eosc", f"{sib_safe}_content.md")
                        with open(sib_md_filename, "w", encoding='utf-8') as f:
                            f.write(sib['markdown'])
                        try:
                            import io
                            vault_sib_filename = os.path.basename(sib_md_filename)
                            sib_bytes = sib['markdown'].encode('utf-8')
                            client.put_object(
                                "vault",
                                vault_sib_filename,
                                data=io.BytesIO(sib_bytes),
                                length=len(sib_bytes),
                                content_type="text/markdown"
                            )
                        except Exception as e:
                            print(f"Warning: Failed to upload sibling markdown to MinIO vault: {e}")
                            
                        doc_links.append({
                            "@type": "CreativeWork",
                            "name": sib['title'],
                            "contentUrl": f"https://mcp.dev.codata.org/vault/{os.path.basename(sib_md_filename)}",
                            "encodingFormat": "text/markdown"
                        })
                
                if slice_links:
                    doc_links.extend(slice_links)

                # Append HTML page metadata (title, meta tags, JSON-LD etc.) extracted by bs4
                if page_meta:
                    doc_links.append(page_meta)
                    

                if extracted_meta:
                    json_data.update(extracted_meta)
                    
                if "isBasedOn" in json_data:
                    if isinstance(json_data["isBasedOn"], list):
                        json_data["isBasedOn"].extend(doc_links)
                    else:
                        json_data["isBasedOn"] = [json_data["isBasedOn"]] + doc_links
                else:
                    json_data["isBasedOn"] = doc_links
                    
                if expert:
                    if "isPartOf" not in json_data:
                        json_data["isPartOf"] = []
                    elif not isinstance(json_data["isPartOf"], list):
                        json_data["isPartOf"] = [json_data["isPartOf"]]
                    json_data["isPartOf"].append({"@type": "Collection", "name": expert})
                    
                if "unmappedFields" in json_data:
                    unmapped = json_data["unmappedFields"]
                    if isinstance(unmapped, list):
                        print(f"⚠ Found {len(unmapped)} unmapped custom field(s):")
                        for field in unmapped:
                            key = field.get("@type", "Unknown")
                            val = str(field.get("value", field))
                            print(f"    - {key}: {val[:80]}{'...' if len(val) > 80 else ''}")
                    else:
                        print(f"⚠ Found unmapped custom field(s): {unmapped}")

                # Recursively sanitize ALL keys in the JSON-LD tree so that no key
                # with spaces or special characters ends up as an invalid URI.
                def sanitize_keys(obj):
                    if isinstance(obj, dict):
                        return {
                            (k if k.startswith('@') else re.sub(r'[^A-Za-z0-9_\-.]', '_', k)): sanitize_keys(v)
                            for k, v in obj.items()
                        }
                    elif isinstance(obj, list):
                        return [sanitize_keys(item) for item in obj]
                    return obj

                json_data = sanitize_keys(json_data)

    
                # Reorder dictionary to put @context and @type at the top
                ordered_data = {}
                
                # Add ODRL policy for Markdown files with language property
                json_data["odrl:hasPolicy"] = {
                    "@type": "odrl:Policy",
                    "odrl:permission": [{
                        "odrl:action": ["odrl:read", "odrl:use"],
                        "odrl:target": {
                            "@type": "odrl:AssetCollection",
                            "odrl:refinement": [
                                {
                                    "odrl:leftOperand": "dc:format",
                                    "odrl:operator": "odrl:eq",
                                    "odrl:rightOperand": "text/markdown"
                                },
                                {
                                    "odrl:leftOperand": "dc:language",
                                    "odrl:operator": "odrl:isPresent"
                                }
                            ]
                        }
                    }]
                }
                
                # Use full Croissant context
                existing_ctx = json_data.pop("@context", None)
                if not existing_ctx or existing_ctx == "https://schema.org":
                    ordered_data["@context"] = {
                        "@vocab": "https://schema.org/",
                        "cr": "http://mlcommons.org/croissant/",
                        "odrl": "http://www.w3.org/ns/odrl/2/",
                        "dc": "http://purl.org/dc/terms/"
                    }
                else:
                    if isinstance(existing_ctx, dict):
                        existing_ctx["odrl"] = "http://www.w3.org/ns/odrl/2/"
                        existing_ctx["dc"] = "http://purl.org/dc/terms/"
                    ordered_data["@context"] = existing_ctx
                    
                ordered_data["@type"] = json_data.pop("@type", "Dataset")
                ordered_data.update(json_data)
                json_data = ordered_data
                
                # Write to temporary file for rdflib
                if user_name or user_email:
                    if "creator" in json_data:
                        existing_creators = json_data.pop("creator")
                        if "author" not in json_data:
                            json_data["author"] = existing_creators
                        else:
                            if not isinstance(json_data["author"], list):
                                json_data["author"] = [json_data["author"]]
                            if isinstance(existing_creators, list):
                                json_data["author"].extend(existing_creators)
                            else:
                                json_data["author"].append(existing_creators)
                                
                    creator_node = {"@type": "Person"}
                    if user_name:
                        creator_node["name"] = user_name
                    if user_email:
                        creator_node["email"] = user_email
                    json_data["creator"] = creator_node
                    
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonld', delete=False) as tf:
                    json.dump(json_data, tf)
                    temp_name = tf.name
                    
                try:
                    g = Graph()
                    g.parse(temp_name, format="json-ld")
                    if len(g) == 0:
                        print("✗ Invalid JSON-LD: Parsed 0 triples. The model generated an invalid schema structure.")
                        if attempt < MAX_RETRIES:
                            print("Retrying...")
                            continue
                        else:
                            print("Aborting conversion. Please retry or check the source content.")
                            return
                    print(f"✓ Valid JSON-LD: Successfully loaded {len(g)} triples into RDF graph.")
                except Exception as e:
                    print(f"✗ Invalid JSON-LD schema or namespaces: {e}")
                    if attempt < MAX_RETRIES:
                        print("Retrying...")
                        continue
                    else:
                        return
                finally:
                    os.remove(temp_name)
                    
                # Check Elasticsearch for existing version and increment if necessary
                if "version" not in json_data:
                    json_data["version"] = "1.0"
                es_version = get_elasticsearch_version(url, expert)
                if es_version:
                    json_data["version"] = str(es_version)
                    print(f"  ✓ Resource already in Elasticsearch. Updating version to {es_version}")
                
                # Overwrite output with the modified json_data
                output = json.dumps(json_data, indent=2)
                break
                
            except json.JSONDecodeError as e:
                print(f"✗ Invalid JSON structure: {e}")
                if attempt < MAX_RETRIES:
                    print("Retrying conversion...")
                    continue
                else:
                    print("Aborting conversion due to invalid JSON after max retries.")
                    return


        output_filename = f"{safe_name}_croissant.jsonld"
        
        with open(output_filename, "w", encoding='utf-8') as f:
            f.write(output)
        print(f"\nOutput saved to {output_filename}")
        
        # --- Index into Ollama with Provenance (only when --reingest or --index is set) ---
        if reingest or index:
            print("\n--- Indexing into Ollama ---")
            index_payload = {
                "model": MODEL_NAME,
                "prompt": f"Store this document in your index for future queries.\n\n{markdown_data}",
                "croissant": json_data,
                "stream": False
            }
            try:
                print("Sending indexing request with Croissant provenance...")
                res_index = requests.post(f"{OLLAMA_HOST}/api/generate", json=index_payload, timeout=600)
                res_index.raise_for_status()
                print("✓ Successfully indexed document with provenance data!")
            except Exception as e:
                print(f"✗ Failed to index document: {e}")
            
        if reingest:
            print("\n--- Ingesting into QLever ---")
            try:
                api_base = os.environ.get("API_BASE", "http://localhost:7013")
                print(f"Sending ingestion request to {api_base}/add_record...")
                res_ql = requests.post(f"{api_base}/add_record", json=json_data, timeout=10)
                res_ql.raise_for_status()
                print(f"✓ Successfully ingested into QLever! Response: {res_ql.text}")
            except Exception as e:
                print(f"✗ Failed to ingest into QLever: {e}")

        if elastic:
            index_into_elasticsearch(url, json_data, markdown_data, expert)

        if upload_gdrive and user_email:
            try:
                # Extract references from the Croissant JSON-LD and append to Markdown
                references = []
                for key in ["citation", "isBasedOn", "url"]:
                    if key in json_data:
                        val = json_data[key]
                        if isinstance(val, list):
                            references.extend(val)
                        else:
                            references.append(val)
                            
                if "unmappedFields" in json_data:
                    for field in json_data["unmappedFields"]:
                        if isinstance(field, dict) and field.get("key", "").lower() in ["references", "reference", "citation", "citations"]:
                            val = field.get("value")
                            if isinstance(val, list):
                                references.extend(val)
                            elif val:
                                references.append(val)
                                
                if references:
                    with open(md_filename, "a", encoding='utf-8') as f:
                        f.write("\n\n---\n## References\n")
                        for i, ref in enumerate(references, 1):
                            # Filter out complex objects and just use their IDs/names or strings
                            ref_text = str(ref)
                            if isinstance(ref, dict):
                                ref_text = ref.get("url", ref.get("name", ref.get("@id", str(ref))))
                            f.write(f"{i}. {ref_text}\n")
                            
                from gdrive_utils import upload_to_gdrive
                print(f"Uploading output to Google Drive folder: {user_email}")
                upload_to_gdrive(user_email, [md_filename], target_folder_id=upload_gdrive_folder)
            except Exception as e:
                print(f"Failed to upload to Google Drive: {e}")

            
    except requests.exceptions.Timeout:
        print(f"Failed to process {url}: Request timed out after 600s")
    except Exception as e:
        print(f"Failed to process {url}: {e}")

def process_spreadsheet(url, is_slice=False, traverse=False, reingest=False, user_name=None, user_email=None, index=False, elastic=False, expert="/expert/croissant", upload_gdrive=False, upload_gdrive_folder=None):
    print(f"Detected Google Spreadsheet URL: {url}")
    # Convert edit url to export url
    if "/edit" in url:
        url = re.sub(r'/edit.*gid=(\d+)', r'/export?format=csv&gid=\1', url)
        url = re.sub(r'/edit.*', r'/export?format=csv', url)
    elif "format=csv" not in url:
        if "?" in url:
            url += "&format=csv"
        else:
            url += "?format=csv"
            
    print(f"Fetching CSV from: {url}")
    try:
        response = scraper.get(url, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch spreadsheet: {e}")
        return

    csv_data = response.text
    reader = csv.DictReader(io.StringIO(csv_data))
    
    urls_to_process = []
    
    url_pattern = re.compile(r'https?://[^\s)\]]+')
    
    for row in reader:
        for val in row.values():
            if val:
                val_str = str(val)
                # Find all URLs in the cell
                matches = url_pattern.findall(val_str)
                for match in matches:
                    # Ignore the original spreadsheet URL if it happens to be embedded
                    if "docs.google.com/spreadsheets" not in match:
                        urls_to_process.append(match.strip())
                    
    urls_to_process = list(set(urls_to_process)) # deduplicate
    
    # If a limit is specified via args (we'll pass it if available), apply it here
    # For now, we will just use a parameter if we added one, or we can check global args
    limit = getattr(args, 'limit', None)
    if limit and limit > 0:
        urls_to_process = urls_to_process[:limit]
        print(f"Limiting to first {limit} URLs.")
        
    print(f"Found {len(urls_to_process)} URLs to process in spreadsheet.")
    
    import concurrent.futures
    workers = getattr(args, 'workers', 4)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(convert_to_croissant, target_url, is_slice, traverse, reingest, user_name, user_email, index, elastic, expert, upload_gdrive, upload_gdrive_folder): target_url
            for target_url in urls_to_process
        }
        
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            target_url = futures[future]
            try:
                future.result()
                print(f"\n[{i}/{len(urls_to_process)}] Completed processing: {target_url}")
            except Exception as e:
                print(f"\n[{i}/{len(urls_to_process)}] Failed processing: {target_url} - {e}")

def process_local_file(file_path, args):
    print(f"\nProcessing local file: {file_path}")
    try:
        if os.path.getsize(file_path) == 0:
            print(f"Skipping empty file: {file_path}")
            return
            
        with open(file_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        if getattr(args, "format", "croissant") == "oai":
            if isinstance(json_data, list):
                if len(json_data) == 1:
                    json_data = json_data[0]
                else:
                    json_data = {"items": json_data}
            json_data = convert_oai_to_croissant(json_data)
            if not json_data:
                print("Could not convert OAI to Croissant, skipping...")
                return

        # Get URL
        url_val = json_data.get("contentUrl") or json_data.get("url")
        if not url_val:
            url_val = f"file://{os.path.abspath(file_path)}"

        # Try to extract markdown data from isBasedOn or nearby file
        markdown_data = ""
        md_path = None
        
        # Check isBasedOn references
        if "isBasedOn" in json_data:
            items = json_data["isBasedOn"] if isinstance(json_data["isBasedOn"], list) else [json_data["isBasedOn"]]
            for item in items:
                if isinstance(item, dict) and item.get("encodingFormat") == "text/markdown" and item.get("contentUrl"):
                    url_ref = item["contentUrl"]
                    if url_ref.startswith("file://"):
                        candidate = url_ref.replace("file://", "")
                        if os.path.exists(candidate):
                            md_path = candidate
                            break
        
        # Check nearby candidate if not found
        if not md_path:
            candidate1 = file_path.replace("_croissant.jsonld", "_content.md").replace(".jsonld", "_content.md")
            candidate2 = file_path.replace("_croissant.jsonld", "_en_content.md").replace(".jsonld", "_en_content.md")
            if os.path.exists(candidate1):
                md_path = candidate1
            elif os.path.exists(candidate2):
                md_path = candidate2

        if md_path and os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                markdown_data = f.read()
            print(f"  Loaded markdown content from: {md_path}")
        else:
            print("  Warning: No markdown content file found.")

        # Validate with Elasticsearch and update version if it exists
        if "version" not in json_data:
            json_data["version"] = "1.0"
        es_version = get_elasticsearch_version(url_val, args.expert)
        if es_version:
            json_data["version"] = str(es_version)
            print(f"  ✓ Resource already in Elasticsearch. Updating version to {es_version}")
            # Rewrite the updated JSON-LD back to the local file
            if getattr(args, "format", "croissant") != "oai":
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, indent=2)

        if args.reingest:
            print("\n--- Ingesting into QLever ---")
            api_base = os.environ.get("API_BASE", "http://localhost:7013")
            res_ql = requests.post(f"{api_base}/add_record", json=json_data, timeout=10)
            res_ql.raise_for_status()
            print(f"✓ Successfully ingested into QLever!")

        if args.elastic:
            index_into_elasticsearch(url_val, json_data, markdown_data, args.expert)

    except Exception as e:
        print(f"✗ Failed to process file {file_path}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert web pages to Croissant JSON-LD.")
    parser.add_argument("url", help="The URL to scrape (e.g. https://ollama.com/library/ornith/tags)")
    parser.add_argument("--slice", action="store_true", help="Enable slice mode to split markdown into pieces with LLM summaries")
    parser.add_argument("--traverse", action="store_true", help="Extract and link all URLs on the same level")
    parser.add_argument("--reingest", action="store_true", help="Automatically ingest the result into QLever database")
    parser.add_argument("--index-ollama", action="store_true", help="Index the result into Ollama (provenance indexing). Implied by --reingest")
    parser.add_argument("--index", type=str, help="Index name for Elasticsearch (e.g., expert/dataverse). Overrides --expert.")
    parser.add_argument("--format", type=str, default="croissant", help="Input format (croissant or oai)")
    parser.add_argument("--elastic", action="store_true", help=f"Index JSON-LD into Elasticsearch (default: {ELASTICSEARCH_URL})")
    parser.add_argument("--user-name", type=str, help="Name of the authenticated user")
    parser.add_argument("--user-email", type=str, help="Email of the authenticated user")
    parser.add_argument("--limit", type=int, help="Limit the number of URLs to process when reading from a spreadsheet")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent workers for processing spreadsheet URLs")
    parser.add_argument("--expert", "-e", type=str, default="/expert/croissant", help="Selected collection for expert.")
    parser.add_argument("--upload-gdrive", action="store_true", help="Upload resulting files to Google Drive using Service Account")
    parser.add_argument("--upload-gdrive-folder", type=str, help="Specific Google Drive folder ID to upload to (bypasses name search)")
    parser.add_argument("--is-file", action="store_true", help="Treat the input URL as a local file to describe (bypasses URL list reading)")
    args = parser.parse_args()
    
    if args.index:
        args.expert = args.index
        
    import glob
    
    if os.path.isdir(args.url):
        print(f"Reading Croissant JSON-LD files from directory: {args.url}")
        files = glob.glob(os.path.join(args.url, "*_croissant.jsonld"))
        if not files:
            files = glob.glob(os.path.join(args.url, "*.jsonld"))
        if not files:
            files = glob.glob(os.path.join(args.url, "*.json"))

        print(f"Found {len(files)} files to process.")
        
        for i, file_path in enumerate(files, 1):
            process_local_file(file_path, args)

    elif os.path.isfile(args.url) and not args.is_file:
        if getattr(args, "format", "croissant") == "oai":
            process_local_file(args.url, args)
            import sys
            sys.exit(0)
            
        print(f"Reading URLs from file: {args.url}")
        with open(args.url, 'r', encoding='utf-8') as f:
            content = f.read()

        urls_to_process = []

        # JSON file: expect an array of {title, url} objects (or just strings)
        if args.url.lower().endswith('.json'):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and 'url' in item:
                            url_val = item['url'].strip()
                            if url_val and url_val not in urls_to_process:
                                urls_to_process.append(url_val)
                        elif isinstance(item, str):
                            url_val = item.strip()
                            if url_val and url_val not in urls_to_process:
                                urls_to_process.append(url_val)
                elif isinstance(data, dict):
                    # single object
                    if 'url' in data:
                        urls_to_process.append(data['url'].strip())
                print(f"Parsed {len(urls_to_process)} URLs from JSON file.")
            except json.JSONDecodeError as e:
                print(f"Warning: could not parse as JSON ({e}), falling back to regex extraction.")
                url_pattern = re.compile(r'https?://[^\s)\]]+')
                for line in content.splitlines():
                    for match in url_pattern.findall(line):
                        url_val = match.strip()
                        if url_val and url_val not in urls_to_process:
                            urls_to_process.append(url_val)
        else:
            # Plain text / markdown file – extract URLs via regex
            url_pattern = re.compile(r'https?://[^\s)\]]+')
            for line in content.splitlines():
                for match in url_pattern.findall(line):
                    url_val = match.strip()
                    if url_val and url_val not in urls_to_process:
                        urls_to_process.append(url_val)

        if args.limit and args.limit > 0:
            urls_to_process = urls_to_process[:args.limit]

        print(f"Found {len(urls_to_process)} URLs to process in file.")

        for i, target_url in enumerate(urls_to_process, 1):
            print(f"\n[{i}/{len(urls_to_process)}] Processing file URL: {target_url}")
            try:
                convert_to_croissant(target_url, args.slice, args.traverse, args.reingest, args.user_name, args.user_email, args.index_ollama, args.elastic, args.expert, args.upload_gdrive, args.upload_gdrive_folder)
            except Exception as e:
                print(f"Failed processing {target_url}: {e}")

                
    elif "docs.google.com/spreadsheets" in args.url:
        process_spreadsheet(args.url, args.slice, args.traverse, args.reingest, args.user_name, args.user_email, args.index_ollama, args.elastic, args.expert)
    else:
        convert_to_croissant(args.url, args.slice, args.traverse, args.reingest, args.user_name, args.user_email, args.index_ollama, args.elastic, args.expert, getattr(args, "upload_gdrive", False), getattr(args, "upload_gdrive_folder", None))
