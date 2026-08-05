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

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
MODEL_NAME = "gemma4-croissant"

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

def fetch_url_markdown(url, traverse=False):
    if "youtube.com" in url or "youtu.be" in url:
        yt_text, yt_meta = fetch_youtube_transcript(url)
        if traverse:
            return yt_text, yt_meta, []
        return yt_text, yt_meta
        
    print(f"Fetching {url}...")
    try:
        response = scraper.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

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
    prompt = f"Translate the following text to English. Preserve all markdown formatting exactly. Output only the translated text.\n\n{text}"
    payload = {
        "model": "gemma4:e2b",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 4096
        }
    }
    try:
        res = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=600)
        if res.status_code == 200:
            return res.json().get('response', '').strip()
    except Exception as e:
        print(f"Translation failed: {e}")
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

        es_doc = dict(json_data)
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
        # Resolve DOI redirects if it's a doi.org link
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
                export_url = f"{base_url}/api/datasets/export?exporter=croissant&persistentId={persistent_id}"
                print(f"Dataverse URL detected. Trying direct Croissant export from {export_url}")
                res = requests.get(export_url, timeout=15)
                if res.status_code == 200:
                    try:
                        return res.json()
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        print(f"Direct export check failed: {e}")
    return None

def convert_to_croissant(url, is_slice=False, traverse=False, reingest=False, user_name=None, user_email=None, index=False, elastic=False, expert="/expert/croissant"):
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
        if not safe_name:
            safe_name = "url_output"
            
        os.makedirs(os.path.join("data", "ca4eosc"), exist_ok=True)
        safe_name = os.path.join("data", "ca4eosc", safe_name)
        output_filename = f"{safe_name}_croissant.jsonld"
        
        with open(output_filename, "w", encoding='utf-8') as f:
            f.write(output)
        print(f"\nOutput saved to {output_filename}")
        
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
    safe_name = safe_name.replace("/", "_").replace(".", "_")
    
    if parsed_url.query:
        qs = urllib.parse.parse_qsl(parsed_url.query)
        for k, v in qs:
            safe_name += "_" + v
            
    if not safe_name:
        safe_name = "url_output"
        
    os.makedirs(os.path.join("data", "ca4eosc"), exist_ok=True)
    safe_name = os.path.join("data", "ca4eosc", safe_name)

    md_filename = f"{safe_name}_content.md"
    with open(md_filename, "w", encoding='utf-8') as f:
        f.write(markdown_data)
    print(f"Extracted markdown saved to {md_filename}")

    lang = "en"
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
        prompt += f" The source documentation is in language code '{lang}'. Please translate the relevant metadata to English and output the Croissant JSON-LD entirely in English."
    prompt += f" Here is the documentation and description extracted from its official page:\n\n{llm_context_data}\n\nExtract relevant information such as the description, authors, license, keywords, tags, or any dataset dependencies into the Croissant metadata if available. Map keywords/tags to the standard schema:keywords property, and extract them EXACTLY as they appear in the text (do not change casing or invent new tags). Ensure 'keywords' is formatted as a JSON array of strings, not a single comma-separated string. IMPORTANT: For any fields or data that do not have a standard mapping in Croissant, include them in the JSON-LD under a custom field called 'unmappedFields' as a list of key-value pairs.\n\nCRITICAL: Do NOT invent, hallucinate, or generate generic information. You MUST extract the name, description, and details directly from the provided text above.\n\nOutput ONLY a valid JSON object. "
    
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
                md_abs_path = os.path.abspath(md_filename)
                doc_links = [{
                    "@type": "CreativeWork",
                    "name": "Scraped Markdown Content",
                    "contentUrl": f"file://{os.path.abspath(original_md_filename)}",
                    "encodingFormat": "text/markdown"
                }]
                
                if original_md_filename != md_filename:
                    doc_links.append({
                        "@type": "CreativeWork",
                        "name": "Translated Markdown Content (English)",
                        "contentUrl": f"file://{md_abs_path}",
                        "encodingFormat": "text/markdown"
                    })
                    
                if traverse and sibling_pages:
                    for sib in sibling_pages:
                        sib_safe = re.sub(r'[^a-zA-Z0-9]', '_', sib['url']).strip('_')
                        sib_md_filename = os.path.join("data", "ca4eosc", f"{sib_safe}_content.md")
                        with open(sib_md_filename, "w", encoding='utf-8') as f:
                            f.write(sib['markdown'])
                        doc_links.append({
                            "@type": "CreativeWork",
                            "name": sib['title'],
                            "contentUrl": f"file://{os.path.abspath(sib_md_filename)}",
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
                
                # Use full Croissant context
                existing_ctx = json_data.pop("@context", None)
                if not existing_ctx or existing_ctx == "https://schema.org":
                    ordered_data["@context"] = {
                        "@vocab": "https://schema.org/",
                        "cr": "http://mlcommons.org/croissant/"
                    }
                else:
                    ordered_data["@context"] = existing_ctx
                    
                ordered_data["@type"] = json_data.pop("@type", "Dataset")
                ordered_data.update(json_data)
                json_data = ordered_data
                
                # Write to temporary file for rdflib
                if user_name or user_email:
                    creator = {"@type": "Person"}
                    if user_name:
                        creator["name"] = user_name
                    if user_email:
                        creator["email"] = user_email
                    json_data["creator"] = creator
                    
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

            
    except requests.exceptions.Timeout:
        print(f"Failed to process {url}: Request timed out after 600s")
    except Exception as e:
        print(f"Failed to process {url}: {e}")

def process_spreadsheet(url, is_slice=False, traverse=False, reingest=False, user_name=None, user_email=None, index=False, elastic=False, expert="/expert/croissant"):
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
            executor.submit(convert_to_croissant, target_url, is_slice, traverse, reingest, user_name, user_email, index, elastic, expert): target_url
            for target_url in urls_to_process
        }
        
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            target_url = futures[future]
            try:
                future.result()
                print(f"\n[{i}/{len(urls_to_process)}] Completed processing: {target_url}")
            except Exception as e:
                print(f"\n[{i}/{len(urls_to_process)}] Failed processing: {target_url} - {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert web pages to Croissant JSON-LD.")
    parser.add_argument("url", help="The URL to scrape (e.g. https://ollama.com/library/ornith/tags)")
    parser.add_argument("--slice", action="store_true", help="Enable slice mode to split markdown into pieces with LLM summaries")
    parser.add_argument("--traverse", action="store_true", help="Extract and link all URLs on the same level")
    parser.add_argument("--reingest", action="store_true", help="Automatically ingest the result into QLever database")
    parser.add_argument("--index", action="store_true", help="Index the result into Ollama (provenance indexing). Implied by --reingest")
    parser.add_argument("--elastic", action="store_true", help=f"Index JSON-LD into Elasticsearch (default: {ELASTICSEARCH_URL})")
    parser.add_argument("--user-name", type=str, help="Name of the authenticated user")
    parser.add_argument("--user-email", type=str, help="Email of the authenticated user")
    parser.add_argument("--limit", type=int, help="Limit the number of URLs to process when reading from a spreadsheet")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent workers for processing spreadsheet URLs")
    parser.add_argument("--expert", "-e", type=str, default="/expert/croissant", help="Selected collection for expert.")
    args = parser.parse_args()
    
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
            print(f"\n[{i}/{len(files)}] Processing local file: {file_path}")
            try:
                if os.path.getsize(file_path) == 0:
                    print(f"Skipping empty file: {file_path}")
                    continue
                    
                with open(file_path, "r", encoding="utf-8") as f:
                    json_data = json.load(f)

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

    elif os.path.isfile(args.url):
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
                convert_to_croissant(target_url, args.slice, args.traverse, args.reingest, args.user_name, args.user_email, args.index, args.elastic, args.expert)
            except Exception as e:
                print(f"Failed processing {target_url}: {e}")

                
    elif "docs.google.com/spreadsheets" in args.url:
        process_spreadsheet(args.url, args.slice, args.traverse, args.reingest, args.user_name, args.user_email, args.index, args.elastic, args.expert)
    else:
        convert_to_croissant(args.url, args.slice, args.traverse, args.reingest, args.user_name, args.user_email, args.index, args.elastic, args.expert)
