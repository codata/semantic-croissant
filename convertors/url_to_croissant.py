GLOBAL_PARSED_TABLES = []
GLOBAL_PDF_ASSETS = []
import io
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
from bs4 import BeautifulSoup
import markdownify
from rdflib import Graph
from youtube_transcript_api import YouTubeTranscriptApi
from playwright.sync_api import sync_playwright

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://10.147.18.82:11435")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
OLLAMA_HEADERS = {"Authorization": f"Bearer {OLLAMA_API_KEY}"} if OLLAMA_API_KEY else {}
def _get_default_es_url():
    raw = os.environ.get("ES_HOST") or os.environ.get("ELASTICSEARCH_URL") or "http://localhost:9200"
    in_docker = bool(os.environ.get("IN_DOCKER")) or os.path.exists("/.dockerenv")
    if in_docker and any(h in raw for h in ["http://localhost:", "http://127.0.0.1:", "http://0.0.0.0:"]):
        import re
        raw = re.sub(r"http://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?", "http://elasticsearch:9200", raw)
    return raw.strip().rstrip("/")

ELASTICSEARCH_URL = _get_default_es_url()
HOST = os.environ.get("HOST", "").strip().rstrip("/")
MCP_DOMAIN = os.environ.get("MCP_DOMAIN", "localhost")
if not HOST and MCP_DOMAIN and MCP_DOMAIN != "localhost":
    HOST = f"https://{MCP_DOMAIN}"
elif not HOST:
    HOST = f"http://{MCP_DOMAIN}"

def get_base_host():
    """Get canonical base host URL (without trailing slash)."""
    h = os.environ.get("HOST", "").strip().rstrip("/")
    if h:
        return h
    dom = os.environ.get("MCP_DOMAIN", "localhost").strip()
    if dom and dom != "localhost":
        return f"https://{dom}"
    return f"http://{dom}"

def get_mcp_domain():
    """Get host domain name without scheme."""
    dom = os.environ.get("MCP_DOMAIN", "").strip()
    if dom:
        return dom
    h = os.environ.get("HOST", "").strip().rstrip("/")
    if h:
        return h.replace("http://", "").replace("https://", "").split("/")[0]
    return "localhost"

OLLAMA_DEFAULT_MODEL = os.environ.get("OLLAMA_DEFAULT_MODEL", os.environ.get("OLLAMA_DEFAULT_MODEL", "gemma4:e2b"))
MODEL_NAME = os.environ.get("OLLAMA_DEFAULT_MODEL") or os.environ.get("MODEL_NAME") or os.environ.get("MODEL") or os.environ.get("OLLAMA_DEFAULT_MODEL", "gemma4:e2b")

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
        title = f"YouTube Video {video_id}"
        description = ""
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
                    title = soup.title.text if soup.title else title
                desc_tag = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
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
        if title == f"YouTube Video {video_id}" or not channel:
            try:
                _oe = scraper.get(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json", timeout=10)
                if _oe.status_code == 200:
                    _oj = _oe.json()
                    if _oj.get("title"):
                        title = _oj["title"]
                    if not channel and _oj.get("author_name"):
                        channel = _oj["author_name"]
            except Exception:
                pass
            
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
        
        _yt_readme = f"# {title}\n\n**URL:** {url}\n"
        if channel: _yt_readme += f"**Channel:** {channel}\n"
        if date: _yt_readme += f"**Published:** {date}\n"
        _yt_readme += f"\n## Description\n\n{description or 'No description available.'}\n"
        globals()['GLOBAL_YOUTUBE_README'] = _yt_readme.encode("utf-8")
        globals()['GLOBAL_YOUTUBE_AGENTS'] = f"# YouTube Transcript: {title}\n\n{text}\n".encode("utf-8")
        
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
            readme_content = None
            for _rm_cand in ("README.md", "README.rst", "README.txt", "README", "readme.md"):
                _cand_res = scraper.get(f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{_rm_cand}", timeout=30)
                if _cand_res.status_code == 200 and _cand_res.text.strip():
                    readme_content = _cand_res.text
                    globals()['GLOBAL_GITHUB_RAW_README'] = _cand_res.content
                    break
            if not readme_content:
                try:
                    _oh = os.environ.get("OLLAMA_HOST", "http://host.docker.internal:11434").rstrip("/")
                    _om = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
                    _gp = f"Write a concise, accurate README.md for the GitHub repository {owner}/{repo}.\nDescription: {repo_info.get('description', '')}\nLanguage: {repo_info.get('language', 'Unknown')}\nTopics: {repo_info.get('topics', [])}\nURL: {url}"
                    _gr = scraper.post(f"{_oh}/api/generate", json={"model": _om, "prompt": _gp, "stream": False}, timeout=60)
                    if _gr.status_code == 200 and _gr.json().get("response", "").strip():
                        readme_content = _gr.json()["response"].strip()
                        globals()['GLOBAL_GITHUB_RAW_README'] = readme_content.encode("utf-8")
                except Exception:
                    pass
            if not readme_content:
                readme_content = f"# {repo_info.get('name', repo)}\n\n{repo_info.get('description', 'No README found.')}"
                globals()['GLOBAL_GITHUB_RAW_README'] = readme_content.encode("utf-8")
            
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

def resolve_direct_url(url):
    """If url is a Google redirect or a vault/doc viewer page, resolve to canonical destination URL."""
    if url and "google.com/goto" in url:
        try:
            r = scraper.get(url, allow_redirects=False, timeout=10)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                resolved = r.headers["Location"].strip()
                print(f"  -> Resolved Google redirect to direct URL: {resolved}")
                return resolved
        except Exception as e:
            print(f"  -> Could not resolve Google redirect for {url}: {e}")
            
    # If the URL is a local vault doc viewer URL (/vault/doc/<id>), resolve it to /vault/doc/raw/<id>
    if url and "/vault/doc/" in url and "/vault/doc/raw/" not in url:
        parts = url.split("/vault/doc/")
        doc_id = parts[1].split("?")[0].split("#")[0].rstrip("/")
        raw_url = parts[0] + "/vault/doc/raw/" + doc_id
        return raw_url

    return url

def fetch_url_markdown(url, traverse=False, use_computer_vision=False):
    url = resolve_direct_url(url)
    if "github.com" in url and "api.github.com" not in url:
        parsed = urllib.parse.urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) == 2:
            res = fetch_github_repo(url, traverse)
            if res:
                return res
                
    if "delpher.nl" in url and "identifier=" in url:
        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        identifier = query_params.get("identifier", [None])[0]
        if identifier:
            ocr_url = f"https://www.delpher.nl/nl/pres/view/pageocr?identifier={identifier}&coll=ddd&operation=download"
            print(f"Detected Delpher article. Fetching OCR text...")
            try:
                response = requests.get(ocr_url, timeout=30)
                if response.status_code == 200:
                    text = response.text.strip()
                    meta = {
                        "name": f"Delpher Article {identifier}",
                        "contentUrl": url,
                    }
                    if traverse:
                        return text, meta, []
                    return text, meta
            except Exception as e:
                print(f"Failed to fetch Delpher text: {e}")

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
                import fitz
                
                import hashlib
                from datetime import datetime, timezone

                pdf_bytes = content_bytes
                checksum = hashlib.sha256(pdf_bytes).hexdigest()
                size = len(pdf_bytes)
                
                print("Detected PDF document. Extracting pages, images, and running OCR pipeline...")
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                text = ""
                global GLOBAL_PDF_ASSETS
                GLOBAL_PDF_ASSETS = []
                
                # Check if Tesseract tessdata is configured or use standard path
                tess_prefix = os.environ.get("TESSDATA_PREFIX", "/usr/share/tesseract-ocr/5/tessdata")
                if not os.path.exists(tess_prefix) and os.path.exists("/usr/share/tessdata/5/tessdata"):
                    tess_prefix = "/usr/share/tessdata/5/tessdata"
                
                for page_idx, page in enumerate(doc, start=1):
                    native_text = (page.get_text() or "").strip()
                    
                    # 1. Render page to high-res JPEG image
                    page_img_bytes = None
                    try:
                        pix = page.get_pixmap(dpi=150)
                        page_img_bytes = pix.tobytes("jpeg")
                        GLOBAL_PDF_ASSETS.append({
                            "type": "page",
                            "page": page_idx,
                            "bytes": page_img_bytes,
                            "filename_suffix": f"_page_{page_idx:02d}.jpg",
                            "mimetype": "image/jpeg",
                            "description": f"Rendered Image of Page {page_idx}"
                        })
                    except Exception as e_pix:
                        print(f"Warning: Failed to render page {page_idx} to image: {e_pix}")
                        
                    # 2. Extract embedded images (>= 200x200) from page
                    try:
                        page_imgs = page.get_images(full=True)
                        extracted_embedded_count = 0
                        for img_idx, img_info in enumerate(page_imgs, start=1):
                            xref = img_info[0]
                            base_img = doc.extract_image(xref)
                            w = base_img.get("width", 0)
                            h = base_img.get("height", 0)
                            ext = base_img.get("ext", "png").lower()
                            if ext == "jpg": ext = "jpeg"
                            # Filter out tiny icon / banner artifacts
                            if w >= 200 and h >= 200:
                                extracted_embedded_count += 1
                                GLOBAL_PDF_ASSETS.append({
                                    "type": "image",
                                    "page": page_idx,
                                    "index": img_idx,
                                    "bytes": base_img.get("image"),
                                    "filename_suffix": f"_page_{page_idx:02d}_img_{img_idx:02d}.{ext}",
                                    "mimetype": f"image/{ext}",
                                    "description": f"Extracted Image from Page {page_idx} ({w}x{h})"
                                })
                    except Exception as e_emb:
                        print(f"Warning: Failed to extract embedded images on page {page_idx}: {e_emb}")

                    # 3. Run OCR on page
                    ocr_text = ""
                    try:
                        tp = page.get_textpage_ocr(language="spa", dpi=150, tessdata=tess_prefix if os.path.exists(tess_prefix) else None)
                        ocr_text = (tp.extractText() or "").strip()
                    except Exception as e_ocr:
                        try:
                            # Fallback without explicit tessdata
                            tp = page.get_textpage_ocr(language="spa", dpi=150)
                            ocr_text = (tp.extractText() or "").strip()
                        except Exception as e_ocr2:
                            print(f"Warning: OCR extraction failed on page {page_idx}: {e_ocr2}")

                    text += f"### Page {page_idx}\n\n"
                    if native_text:
                        text += f"**Native Text:**\n{native_text}\n\n"
                    if ocr_text and ocr_text != native_text:
                        text += f"**OCR Text:**\n{ocr_text}\n\n"
                    if not native_text and not ocr_text:
                        text += "_[No text detected on page]_\n\n"
                
                print(f"PDF processed: {len(doc)} pages, {len(GLOBAL_PDF_ASSETS)} page renders & extracted images, text length={len(text)}")
                    
                try:
                    import sys as _sys
                    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                    import datamaps_runner
                except Exception:
                    datamaps_runner = None

                use_datamaps_cv = bool(datamaps_runner and datamaps_runner.url_matches(url))
                if use_datamaps_cv:
                    print("URL matches DATAMAPS_URL_PATTERNS, running datamaps CV pipeline...")
                    try:
                        dm_result = datamaps_runner.run(url)
                    except Exception as e_dm:
                        print(f"Warning: datamaps pipeline failed: {e_dm}")
                elif use_computer_vision:
                        print("Running Computer Vision extraction on PDF with Palefire...")
                        cv_done = False
                        palefire_url = os.environ.get("PALEFIRE_API_URL", "http://10.147.18.24:8000/parse-url")
                        try:
                            print(f"Calling Palefire API service at {palefire_url}...")
                            vision_model = os.environ.get("VISION_MODEL", "gemma4:31b-cloud")
                            resp = requests.post(
                                palefire_url,
                                json={
                                    "url": url,
                                    "vision_extract": True,
                                    "vision_model": vision_model
                                },
                                timeout=600
                            )
                            if resp.status_code == 200:
                                data = resp.json()
                                episodes = data.get("episodes", [])
                                cv_text_blocks = []
                                for ep in episodes:
                                    if isinstance(ep, dict):
                                        cnt = ep.get("content", {})
                                        analysis = cnt.get("analysis", "") if isinstance(cnt, dict) else str(cnt)
                                        src = cnt.get("source_file", "") if isinstance(cnt, dict) else ""
                                        if analysis:
                                            cv_text_blocks.append(f"### Visual Analysis ({src})\n{analysis}")
                                if cv_text_blocks:
                                    text += "\n\n## Computer Vision Extracted Insights & Maps\n\n" + "\n\n".join(cv_text_blocks) + "\n"
                                    print(f"Successfully added {len(cv_text_blocks)} visual analysis blocks from Palefire API.")
                                    cv_done = True
                                elif data.get("text"):
                                    # If palefire returned full text with CV integrated
                                    if "## Computer Vision" in data.get("text", ""):
                                        text = data["text"]
                                        cv_done = True
                            else:
                                print(f"Palefire API returned status {resp.status_code}: {resp.text[:200]}")
                        except Exception as e_api:
                            print(f"Palefire API call failed: {e_api}")

                        if not cv_done:
                            print("Fallback: Attempting local Palefire CV script execution...")
                            try:
                                import tempfile, subprocess
                                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
                                    tmp_pdf.write(pdf_bytes)
                                    tmp_pdf_path = tmp_pdf.name
                                
                                out_ep_file = tmp_pdf_path + "_episodes.json"
                                palefire_cv_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "../palefire/extract_computer_vision.py"))
                                if not os.path.exists(palefire_cv_script):
                                    palefire_cv_script = "palefire/extract_computer_vision.py"
                                    
                                cv_cmd = [
                                    "python3", palefire_cv_script,
                                    "--pdf", tmp_pdf_path,
                                    "--vision-model", os.environ.get("VISION_MODEL", "gemma4:31b-cloud"),
                                    "--output", out_ep_file
                                ]
                                print(f"Executing: {' '.join(cv_cmd)}")
                                subprocess.run(cv_cmd, check=True, timeout=600)
                                
                                if os.path.exists(out_ep_file):
                                    with open(out_ep_file, 'r', encoding='utf-8') as f_ep:
                                        episodes = json.load(f_ep)
                                    cv_text_blocks = []
                                    for ep in episodes:
                                        if isinstance(ep, dict):
                                            cnt = ep.get("content", {})
                                            analysis = cnt.get("analysis", "") if isinstance(cnt, dict) else str(cnt)
                                            src = cnt.get("source_file", "") if isinstance(cnt, dict) else ""
                                            if analysis:
                                                cv_text_blocks.append(f"### Visual Analysis ({src})\n{analysis}")
                                    if cv_text_blocks:
                                        text += "\n\n## Computer Vision Extracted Insights & Maps\n\n" + "\n\n".join(cv_text_blocks) + "\n"
                                    try:
                                        os.unlink(out_ep_file)
                                    except Exception:
                                        pass
                                try:
                                    os.unlink(tmp_pdf_path)
                                except Exception:
                                    pass
                            except Exception as e_cv:
                                print(f"Warning: Local computer vision extraction failed: {e_cv}")
                    
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

        # Check for image formats (JPG, PNG, WEBP, TIFF, BMP)
        IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.tiff', '.bmp')
        is_image = any(url.lower().endswith(ie) for ie in IMAGE_EXTS) or content_type.startswith('image/') or content_bytes.startswith(b'\xff\xd8') or content_bytes.startswith(b'\x89PNG\r\n\x1a\n')

        if is_image:
            try:
                import hashlib
                from datetime import datetime, timezone

                checksum = hashlib.sha256(content_bytes).hexdigest()
                size = len(content_bytes)

                print("Detected image file. Performing Tesseract OCR via PaleFire ImageParser...")
                ocr_text = ""
                img_dims = ""

                # First call PaleFire parse endpoint (uses PaleFire's ImageParser with Tesseract)
                try:
                    import requests
                    filename = url.split('/')[-1] if '/' in url else "image.jpg"
                    data_payload = {}
                    if 'args' in globals() and getattr(args, 'engine', None):
                        data_payload['engine'] = args.engine
                    if 'args' in globals() and getattr(args, 'ollama_visual_model', None):
                        data_payload['ollama_visual_model'] = args.ollama_visual_model
                    elif os.environ.get("OLLAMA_VISUAL_MODEL"):
                        data_payload['ollama_visual_model'] = os.environ.get("OLLAMA_VISUAL_MODEL")
                    resp = requests.post(
                        "http://palefire-api:8000/parse",
                        files={"file": (filename, content_bytes, content_type or "image/jpeg")},
                        data=data_payload,
                        timeout=300
                    )
                    if resp.status_code == 200:
                        parsed_json = resp.json()
                        if parsed_json.get("success"):
                            ocr_text = parsed_json.get("text", "").strip()
                            meta_pf = parsed_json.get("metadata", {})
                            w = meta_pf.get("width")
                            h = meta_pf.get("height")
                            if w and h:
                                img_dims = f"{w}x{h}"
                            # Save extracted tables to CSV/XLSX if available
                            tbls = parsed_json.get("tables", [])
                            if tbls and isinstance(tbls, list):
                                try:
                                    import pandas as pd
                                    import io
                                    for t_idx, tbl in enumerate(tbls):
                                        t_headers = tbl.get("headers")
                                        t_rows = tbl.get("rows")
                                        t_name = tbl.get("name") or f"table_{t_idx}"
                                        t_month = tbl.get("month_name") or ""
                                        if t_headers and t_rows:
                                            df_tbl = pd.DataFrame(t_rows, columns=t_headers)
                                            # Put in GLOBAL_PARSED_TABLES for upload after safe_name is computed
                                            GLOBAL_PARSED_TABLES.append({
                                                'df': df_tbl,
                                                'name': t_name,
                                                'month_name': t_month,
                                                'index': t_idx
                                            })
                                except Exception as e_tbl:
                                    print(f"Warning: Failed to convert parsed table to DataFrame: {e_tbl}")
                except Exception as e_pf:
                    print(f"PaleFire parser service error: {e_pf}")

                # Local fallback via tesseract CLI / pytesseract if direct
                if not ocr_text:
                    for psm in [6, 3, 11]:
                        try:
                            import subprocess
                            res = subprocess.run(
                                ["tesseract", "stdin", "stdout", "-l", "spa+eng", "--psm", str(psm)],
                                input=content_bytes,
                                capture_output=True,
                                timeout=30
                            )
                            if res.returncode == 0 and res.stdout.strip():
                                ocr_text = res.stdout.decode("utf-8", errors="replace").strip()
                                break
                        except Exception:
                            pass

                # Image dimension inspection via fitz/pymupdf if not already detected
                if not img_dims:
                    try:
                        import fitz
                        doc_img = fitz.open(stream=content_bytes, filetype=url.split('.')[-1].lower() if '.' in url else "jpg")
                        if len(doc_img) > 0:
                            p = doc_img[0]
                            img_dims = f"{int(p.rect.width)}x{int(p.rect.height)}"
                    except Exception:
                        pass

                if ocr_text.startswith("# Daily Rainfall Measurements") or ocr_text.startswith("# Map Analysis:"):
                    text = ocr_text
                else:
                    text = f"# Image Document: {url.split('/')[-1]}\n\n"
                    if img_dims:
                        text += f"**Dimensions:** {img_dims} pixels\n"
                    text += f"**OCR Engine:** Tesseract OCR (PaleFire ImageParser)\n\n"
                    text += "## Extracted Text Content\n\n"
                    text += ocr_text if ocr_text else "_[No text detected by OCR]_"

                fmt = "image/jpeg" if (url.lower().endswith(('.jpg', '.jpeg')) or content_bytes.startswith(b'\xff\xd8')) else (content_type or "image/png")
                meta = {
                    "name": url.split('/')[-1] or "Image File",
                    "contentUrl": url,
                    "encodingFormat": fmt,
                    "contentSize": f"{size} B",
                    "sha256": checksum,
                    "retrievalTimestamp": datetime.now(timezone.utc).isoformat(),
                }
                if 'meta_pf' in locals() and isinstance(meta_pf, dict):
                    if meta_pf.get('initial_croissant'):
                        meta['initial_croissant'] = meta_pf.get('initial_croissant')
                    if meta_pf.get('visual_category'):
                        meta['visual_category'] = meta_pf.get('visual_category')
                    if meta_pf.get('temporal_resolution'):
                        meta['temporal_resolution'] = meta_pf.get('temporal_resolution')
                    if meta_pf.get('temporal_period'):
                        meta['temporal_period'] = meta_pf.get('temporal_period')
                if traverse:
                    return text.strip(), meta, []
                return text.strip(), meta
            except Exception as e_img:
                print(f"Failed to process image with OCR: {e_img}")

        if is_local:
            try:
                html_text = content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                html_text = content_bytes.decode('latin-1')
        else:
            html_text = response.text
            is_delpher_search = "delpher.nl" in url and "results" in url
            if is_delpher_search or ("JavaScript is disabled" in html_text and "verify that you're not a robot" in html_text) or response.status_code in (202, 403):
                print(f"Triggering Playwright fallback (is_delpher_search={is_delpher_search})...")
                pw_content = fetch_with_playwright(url)
                if pw_content:
                    html_text = pw_content
            else:
                response.raise_for_status()

        # If not HTML (e.g. raw markdown text or text/plain), return as raw text directly
        if not (html_text.strip().lower().startswith('<!doctype html') or '<html' in html_text.lower() or '<body' in html_text.lower()):
            page_meta = {
                "@type": "CreativeWork",
                "name": url.split('/')[-1] or "Document",
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

            if use_computer_vision and content:
                try:
                    import base64 as _b64
                    import requests as _requests
                    img_urls = []
                    seen_imgs = set()
                    for img in content.find_all('img'):
                        src = img.get('data-src') or img.get('data-lazy-src') or img.get('src')
                        if not src or src.startswith('data:'):
                            continue
                        full_img_url = urllib.parse.urljoin(url, src)
                        low = full_img_url.lower()
                        if any(low.endswith(ext) for ext in ('.svg', '.ico', '.gif')) or any(k in low for k in ('logo', 'icon', 'avatar', 'spinner', 'pixel')):
                            continue
                        if full_img_url not in seen_imgs:
                            seen_imgs.add(full_img_url)
                            img_urls.append(full_img_url)
                    if img_urls:
                        ollama_host = os.environ.get("OLLAMA_HOST", "http://10.147.18.82:11434").rstrip("/")
                        vision_model = os.environ.get("VISION_MODEL", "gemma4:e4b")
                        ocr_blocks = []
                        for idx_cv, img_url in enumerate(img_urls[:5], 1):
                            try:
                                img_resp = _requests.get(img_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                                if img_resp.status_code != 200 or len(img_resp.content) < 5000:
                                    continue
                                # Deposit image to MinIO vault BEFORE OCR / datamaps analysis
                                try:
                                    import hashlib as _hl
                                    from minio import Minio as _Minio
                                    _murl = os.environ.get("MINIO_URL", "http://minio:9000")
                                    if (bool(os.environ.get("IN_DOCKER")) or os.path.exists("/.dockerenv")) and any(h in _murl for h in ["localhost", "127.0.0.1", "0.0.0.0"]):
                                        _murl = "http://minio:9000"
                                    _mc = _Minio(_murl.replace("http://", "").replace("https://", "").rstrip("/"),
                                                 access_key=os.environ.get("MINIO_ROOT_USER", "minioadmin"),
                                                 secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin"),
                                                 secure=_murl.startswith("https"))
                                    _ext = os.path.splitext(img_url.split("?")[0])[1].lower() or ".jpg"
                                    if _ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                                        _ext = ".jpg"
                                    _ctype = img_resp.headers.get("Content-Type", "image/jpeg")
                                    _img_key = f"{_hl.md5(img_resp.content).hexdigest()[:16]}_image_{idx_cv}{_ext}"
                                    _mc.put_object("vault", _img_key, io.BytesIO(img_resp.content), len(img_resp.content), content_type=_ctype)
                                    _g_up = globals()
                                    if 'GLOBAL_HTML_CV_UPLOADED_IMAGES' not in _g_up or _g_up['GLOBAL_HTML_CV_UPLOADED_IMAGES'] is None:
                                        _g_up['GLOBAL_HTML_CV_UPLOADED_IMAGES'] = []
                                    _g_up['GLOBAL_HTML_CV_UPLOADED_IMAGES'].append((_img_key, _ctype, img_url))
                                    print(f"Deposited HTML CV image {_img_key} to vault before OCR analysis.")
                                except Exception as e_dep:
                                    print(f"  -> Pre-OCR vault deposit skipped for {img_url}: {e_dep}")

                                # Try PaleFire datamaps polygon-matching pipeline first for map images
                                try:
                                    dm_img_resp = _requests.post(
                                        "http://palefire-api:8000/datamaps/image",
                                        json={"url": img_url, "page_url": url},
                                        timeout=600,
                                    )
                                    if dm_img_resp.status_code == 200 and dm_img_resp.json().get("status") == "success":
                                        csv_txt = dm_img_resp.json().get("csv_text", "")
                                        if csv_txt.strip():
                                            import io as _io, pandas as _pd
                                            df_dm = _pd.read_csv(_io.StringIO(csv_txt))
                                            _g = globals()
                                            if 'GLOBAL_PARSED_TABLES' not in _g or _g['GLOBAL_PARSED_TABLES'] is None:
                                                _g['GLOBAL_PARSED_TABLES'] = []
                                            _g['GLOBAL_PARSED_TABLES'].append({'df': df_dm, 'month_name': f"Datamap_{len(_g['GLOBAL_PARSED_TABLES'])+1}"})
                                            print(f"PaleFire datamaps extracted {len(df_dm)} polygon rows from {img_url}")
                                except Exception as e_dm_img:
                                    print(f"  -> Datamaps image call skipped/failed for {img_url}: {e_dm_img}")

                                img_b64 = _b64.b64encode(img_resp.content).decode("utf-8")
                                print(f"Running Ollama Vision OCR ({vision_model}) on image: {img_url}")
                                ov_resp = _requests.post(
                                    f"{ollama_host}/api/generate",
                                    json={
                                        "model": vision_model,
                                        "prompt": "Perform OCR and extract all visible text, numbers, labels, legends, regions, and tabular data from this image. Format any structured data as clean Markdown tables.",
                                        "images": [img_b64],
                                        "stream": False,
                                    },
                                    headers=({"Authorization": f"Bearer {os.environ.get('NODE15_API_KEY') or os.environ.get('OLLAMA_API_KEY')}"} if (os.environ.get('NODE15_API_KEY') or os.environ.get('OLLAMA_API_KEY')) else {}),
                                    timeout=120,
                                )
                                if ov_resp.status_code == 200:
                                    ocr_text = ov_resp.json().get("response", "").strip()
                                    if ocr_text:
                                        ocr_blocks.append(f"### Image: {img_url}\n\n{ocr_text}")
                                else:
                                    print(f"  -> Ollama Vision OCR returned HTTP {ov_resp.status_code}: {ov_resp.text[:200]}")
                            except Exception as e_img:
                                print(f"  -> Vision OCR failed for {img_url}: {e_img}")
                        if ocr_blocks:
                            markdown_content += "\n\n## Computer Vision Extracted Image Data\n\n" + "\n\n".join(ocr_blocks)
                            try:
                                import pandas as _pd
                                _g = globals()
                                if 'GLOBAL_PARSED_TABLES' not in _g or _g['GLOBAL_PARSED_TABLES'] is None:
                                    _g['GLOBAL_PARSED_TABLES'] = []
                                for block in ocr_blocks:
                                    lines = [ln.strip() for ln in block.splitlines() if ln.strip().startswith('|') and ln.strip().endswith('|')]
                                    if len(lines) >= 3:
                                        # Split into separate tables if there are multiple header+separator pairs
                                        cur_rows = []
                                        for ln in lines:
                                            cells = [c.strip() for c in ln.strip('|').split('|')]
                                            if all(set(c) <= set('-: ') for c in cells if c):
                                                continue
                                            cur_rows.append(cells)
                                        if len(cur_rows) >= 2:
                                            hdr = cur_rows[0]
                                            body = [r[:len(hdr)] + [''] * max(0, len(hdr) - len(r)) for r in cur_rows[1:]]
                                            df_ocr = _pd.DataFrame(body, columns=hdr)
                                            _g['GLOBAL_PARSED_TABLES'].append({'df': df_ocr, 'month_name': f"Vision_Table_{len(_g['GLOBAL_PARSED_TABLES'])+1}"})
                            except Exception as e_tbl:
                                print(f"Warning: Failed to convert Vision OCR Markdown tables to DataFrame: {e_tbl}")
                except Exception as e_cv:
                    print(f"Warning: HTML Computer Vision image extraction failed: {e_cv}")

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
    model_name = os.environ.get("MODEL") or os.environ.get("MODEL_NAME") or os.environ.get("OLLAMA_DEFAULT_MODEL", os.environ.get("OLLAMA_DEFAULT_MODEL", "gemma4:e2b"))
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 4096
        }
    }
    print(f"DEBUG: Payload sent to Ollama: {repr(payload)}")
    try:
        res = requests.post(f"{ollama_host}/api/generate", json=payload, headers=OLLAMA_HEADERS, timeout=600)
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
            "@vocab": "http://schema.org/",
            "cr": "http://mlcommons.org/croissant/",
            "sc": "http://schema.org/",
            "schema": "http://schema.org/",
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
def check_dspace_direct_export(url):
    import xml.etree.ElementTree as ET
    try:
        parts = urllib.parse.urlparse(url)
        if '/handle/' not in parts.path:
            return None
            
        host = parts.netloc
        handle = parts.path.split('/handle/')[-1]
        oai_url = f"https://{host}/dspace-oai/request?verb=GetRecord&metadataPrefix=datacite&identifier=oai:{host}:{handle}"
        print(f"DSpace URL detected. Fetching OAI-PMH record from {oai_url}")
        
        res = requests.get(oai_url, timeout=15)
        if res.status_code != 200:
            return None
            
        root = ET.fromstring(res.content)
        namespaces = {
            'oai': 'http://www.openarchives.org/OAI/2.0/',
            'datacite': 'http://datacite.org/schema/kernel-4'
        }
        
        record = root.find('.//oai:record/oai:metadata/datacite:resource', namespaces)
        if record is None:
            return None
            
        title_node = record.find('.//datacite:title', namespaces)
        title = title_node.text if title_node is not None else ""
        
        pub_node = record.find('.//datacite:publisher', namespaces)
        publisher = pub_node.text if pub_node is not None else ""
        
        year_node = record.find('.//datacite:publicationYear', namespaces)
        pub_year = year_node.text if year_node is not None else ""
        
        creators = []
        for creator in record.findall('.//datacite:creator/datacite:creatorName', namespaces):
            if creator.text: creators.append({"@type": "Person", "name": creator.text})
            
        keywords = []
        for subj in record.findall('.//datacite:subject', namespaces):
            if subj.text: keywords.append(subj.text)
            
        desc = []
        for d in record.findall('.//datacite:description', namespaces):
            if d.text: desc.append(d.text)
            
        croissant = {
            "@context": {
                "@vocab": "http://schema.org/",
                "sc": "http://schema.org/",
                "schema": "http://schema.org/",
                "citeAs": "cr:citeAs",
                "column": "cr:column",
                "conformsTo": "dct:conformsTo",
                "cr": "http://mlcommons.org/croissant/",
                "data": {"@id": "cr:data", "@type": "@json"},
                "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
                "dct": "http://purl.org/dc/terms/",
                "extract": "cr:extract",
                "field": "cr:field",
                "fileProperty": "cr:fileProperty",
                "fileObject": "cr:fileObject",
                "fileSet": "cr:fileSet",
                "format": "cr:format",
                "includes": "cr:includes",
                "isLiveDataset": "cr:isLiveDataset",
                "jsonPath": "cr:jsonPath",
                "key": "cr:key",
                "md5": "cr:md5",
                "parentField": "cr:parentField",
                "path": "cr:path",
                "recordSet": "cr:recordSet",
                "references": "cr:references",
                "regex": "cr:regex",
                "repeated": "cr:repeated",
                "replace": "cr:replace",
                "separator": "cr:separator",
                "source": "cr:source",
                "subField": "cr:subField",
                "transform": "cr:transform"
            },
            "@type": "sc:Dataset",
            "conformsTo": "http://mlcommons.org/croissant/1.0",
            "name": title,
            "description": "\n".join(desc),
            "url": url,
            "datePublished": pub_year,
            "publisher": {"@type": "Organization", "name": publisher} if publisher else None,
            "creator": creators,
            "keywords": keywords,
            "distribution": []
        }
        
        croissant = {k: v for k, v in croissant.items() if v}
        return croissant
    except Exception as e:
        print(f"DSpace export failed: {e}")
        return None


def check_dataverse_direct_export(url):
    try:
        headers = {'User-Agent': 'SemanticCroissant/1.0'}
        if "doi.org" in url:
            res = requests.head(url, allow_redirects=True, timeout=10, headers=headers)
            target_url = res.url
        else:
            target_url = url
            
        if "persistentId=" in target_url:
            parsed = urllib.parse.urlparse(target_url)
            query = urllib.parse.parse_qs(parsed.query)
            persistent_id = query.get("persistentId", [""])[0]
            if persistent_id:
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                if persistent_id.startswith("doi:"):
                    encoded_pid = urllib.parse.quote(persistent_id, safe='/')
                else:
                    encoded_pid = urllib.parse.quote(persistent_id, safe='')
                
                for exporter in ["croissant", "schema.org"]:
                    export_url = f"{base_url}/api/datasets/export?exporter={exporter}&persistentId={encoded_pid}"
                    print(f"Dataverse URL detected. Trying direct export from {export_url}")
                    res = requests.get(export_url, timeout=15, headers=headers)
                    
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

def fix_croissant_dataverse_distributions(data):
    if not isinstance(data, dict):
        return data
    dataset_url = data.get('url', '')
    dists = data.get('distribution') or data.get('fileObject') or data.get('fileSet') or []
    if not dists or not isinstance(dists, list):
        return data
    has_dataverse_dists = any(isinstance(d, dict) and 'dataverse' in d.get('contentUrl', '') for d in dists)
    if not ('dataverse' in dataset_url or 'doi.org' in dataset_url or has_dataverse_dists):
        return data

    dv_base = None
    pid = None
    for d in dists:
        if isinstance(d, dict) and 'contentUrl' in d and 'dataverse' in d['contentUrl']:
            p = urllib.parse.urlparse(d['contentUrl'])
            dv_base = f"{p.scheme}://{p.netloc}"
            break
    if not dv_base:
        return data

    if 'persistentId=' in dataset_url:
        pid = urllib.parse.parse_qs(urllib.parse.urlparse(dataset_url).query).get('persistentId', [None])[0]
    elif 'doi.org/' in dataset_url:
        doi = dataset_url.split('doi.org/')[-1]
        pid = f"doi:{doi}"
    elif isinstance(data.get('identifier'), str) and 'doi:' in data.get('identifier'):
        pid = data.get('identifier')

    if not pid:
        return data

    api_url = f"{dv_base}/api/datasets/:persistentId/?persistentId={urllib.parse.quote(pid, safe='/')}"
    headers = {'User-Agent': 'SemanticCroissant/1.0'}
    try:
        r_api = requests.get(api_url, headers=headers, timeout=10)
        if r_api.status_code != 200:
            return data
        raw_files = r_api.json().get('data', {}).get('latestVersion', {}).get('files', [])
        api_by_name = {}
        api_by_id = {}
        for f in raw_files:
            df = f.get('dataFile', {})
            fid = df.get('id')
            fn = df.get('filename')
            orig_fn = df.get('originalFileName') or fn
            lbl = f.get('label') or fn
            api_by_id[fid] = df
            if fn: api_by_name[fn] = df
            if orig_fn: api_by_name[orig_fn] = df
            if lbl: api_by_name[lbl] = df

        base_host = get_base_host()
        ds_for_export = data.get('url') or data.get('identifier')
        for d in dists:
            if not isinstance(d, dict): continue
            name = d.get('name')
            md5 = d.get('md5')
            matched_df = api_by_name.get(name)
            if not matched_df and md5:
                for df in api_by_id.values():
                    if df.get('md5') == md5 or df.get('checksum', {}).get('value') == md5:
                        matched_df = df
                        break
            if matched_df:
                d['contentUrl'] = f"{dv_base}/api/access/datafile/{matched_df.get('id')}"
                if matched_df.get('contentType'):
                    d['encodingFormat'] = matched_df.get('contentType')
                if matched_df.get('filesize'):
                    d['contentSize'] = str(matched_df.get('filesize'))

            curl = d.get('contentUrl')
            if curl:
                fn = d.get('name') or (d.get('@id') if isinstance(d.get('@id'), str) and not d.get('@id').startswith('http') else 'file')
                if ds_for_export:
                    export_url = f"{base_host}/export?ds={urllib.parse.quote(ds_for_export, safe='')}&file={urllib.parse.quote(curl, safe='')}"
                else:
                    export_url = f"{base_host}/export?file={urllib.parse.quote(curl, safe='')}"
                d['subjectOf'] = {
                    "@type": "Dataset",
                    "@id": export_url,
                    "encodingFormat": "application/ld+json",
                    "conformsTo": "https://ddialliance.org/Specification/DDI-CDI/1.0/"
                }
    except Exception as e:
        print(f"Failed to align Dataverse distributions: {e}")
    return data


def generate_markdown_from_jsonld(data):
    data = fix_croissant_dataverse_distributions(data)
    md = []
    name = data.get('name', 'Dataset')
    md.append(f"# 🥐 {name}\n")
    url = data.get('url')
    if url:
        md.append(f"**[Original URL \u2192]({url})**\n")
    desc = data.get('description')
    if desc:
        md.append(f"> {desc}\n")
    md.append("---\n")
    
    md.append("### Core Metadata\n")
    md.append("| Field | Value |")
    md.append("|---|---|")
    skip_keys = ['@context', '@type', 'name', 'url', 'description', 'distribution', 'recordSet', 'fileObject', 'fileSet', '_source_url', '_markdown_text', '_full_text']
    for key, value in data.items():
        if key in skip_keys:
            continue
        val_md = ""
        if isinstance(value, dict):
            val_md = value.get('name') or value.get('url') or str(value)
        elif isinstance(value, list):
            val_md = ", ".join([v.get('name') or v.get('url') or str(v) if isinstance(v, dict) else str(v) for v in value])
        else:
            s_val = str(value)
            val_md = f"[{s_val}]({s_val})" if s_val.startswith('http') else s_val
        val_md = val_md.replace('|', '\\|').replace('\n', ' ')
        md.append(f"| **{key}** | {val_md} |")
    md.append("\n")
    
    dists = data.get('distribution') or data.get('fileObject') or data.get('fileSet')
    if dists and isinstance(dists, list) and len(dists) > 0:
        md.append("### Files & Distributions\n")
        md.append("| File | Title | Format | Size | Download | CDIF | Tools |")
        md.append("|---|---|---|---|:---:|:---:|:---:|")
        for d in dists:
            d_name = d.get('name') or d.get('@id') or 'File'
            d_title = d.get('title') or d.get('description') or d.get('headline') or d.get('alternateName') or '-'
            fmt = d.get('encodingFormat') or '-'
            size = d.get('contentSize') or '-'
            curl = d.get('contentUrl')
            dl_str = f"[📥]({curl})" if curl else "-"
            cdif_str = "-"
            tools_str = "[⚙️](#tools)" if curl else "-"
            if curl:
                ds_for_export = data.get('url') or data.get('identifier')
                if ds_for_export:
                    import urllib.parse
                    export_url = f"/export?ds={urllib.parse.quote(ds_for_export, safe='')}&file={urllib.parse.quote(curl, safe='')}"
                    cdif_str = f"[⚡]({export_url})"
            clean_name = str(d_name).replace('|', '\\|')
            clean_title = str(d_title).replace('|', '\\|').replace('\n', ' ')
            clean_fmt = str(fmt).replace('|', '\\|')
            clean_size = str(size).replace('|', '\\|')
            md.append(f"| **{clean_name}** | {clean_title} | {clean_fmt} | {clean_size} | {dl_str} | {cdif_str} | {tools_str} |")
        md.append("\n")
        
    record_sets = data.get('recordSet')
    if record_sets and isinstance(record_sets, list):
        md.append("### Record Sets (Schema)\n")
        ds_for_export = data.get('url') or data.get('identifier')
        for rs in record_sets:
            rs_name = rs.get('name', 'Record Set')
            md.append(f"#### {rs_name}")
            
            # Determine source file and CDIF link
            file_id = None
            rs_src = rs.get('data') or rs.get('source') or {}
            if isinstance(rs_src, dict):
                file_id = rs_src.get('@id') or (rs_src.get('fileObject', {}).get('@id') if isinstance(rs_src.get('fileObject'), dict) else rs_src.get('fileObject'))
            elif isinstance(rs_src, str):
                file_id = rs_src
                
            if not file_id and rs.get('field') and isinstance(rs.get('field'), list):
                for f in rs.get('field'):
                    f_src = f.get('source')
                    if isinstance(f_src, dict):
                        fo = f_src.get('fileObject')
                        if isinstance(fo, dict) and fo.get('@id'):
                            file_id = fo.get('@id')
                            break
                        elif isinstance(fo, str):
                            file_id = fo
                            break
                        elif f_src.get('@id'):
                            file_id = f_src.get('@id')
                            break
                            
            matched_dist = None
            if dists and isinstance(dists, list):
                for d in dists:
                    if not isinstance(d, dict): continue
                    if file_id and (d.get('@id') == file_id or d.get('name') == file_id):
                        matched_dist = d
                        break
                if not matched_dist and file_id:
                    for d in dists:
                        if not isinstance(d, dict): continue
                        d_name = str(d.get('name', ''))
                        if d_name and (d_name.endswith(str(file_id)) or str(file_id).endswith(d_name)):
                            matched_dist = d
                            break
                if not matched_dist and len(dists) == 1 and isinstance(dists[0], dict):
                    matched_dist = dists[0]
                    
            source_file_name = (matched_dist.get('name') or matched_dist.get('@id')) if matched_dist else file_id
            cdif_export_url = None
            if matched_dist and matched_dist.get('contentUrl'):
                curl = matched_dist.get('contentUrl')
                import urllib.parse
                if ds_for_export:
                    cdif_export_url = f"/export?ds={urllib.parse.quote(ds_for_export, safe='')}&file={urllib.parse.quote(curl, safe='')}"
                else:
                    cdif_export_url = f"/export?file={urllib.parse.quote(curl, safe='')}"
            elif matched_dist and isinstance(matched_dist.get('subjectOf'), dict):
                cdif_export_url = matched_dist.get('subjectOf', {}).get('@id')
                
            info_line = []
            if source_file_name:
                info_line.append(f"**Source File:** `{source_file_name}`")
            if cdif_export_url:
                info_line.append(f"**CDIF:** [⚡ Download CDIF]({cdif_export_url})")
            if info_line:
                md.append(f"{' &nbsp;|&nbsp; '.join(info_line)}\n")

            rs_desc = rs.get('description')
            if rs_desc: md.append(f"{rs_desc}\n")
            fields = rs.get('field')
            if fields and isinstance(fields, list):
                md.append("| Field | Type | Description |")
                md.append("|---|---|---|")
                for f in fields:
                    f_name = f.get('name', '')
                    f_type = f.get('dataType') or f.get('cr:dataType') or ''
                    f_type = str(f_type).replace('sc:', '')
                    raw_desc = f.get('description', '')
                    if not raw_desc or raw_desc.strip().lower() == f_name.strip().lower():
                        f_desc = '-'
                    else:
                        f_desc = raw_desc.replace('|', '\\|').replace('\n', ' ')
                    md.append(f"| **{f_name}** | `{f_type}` | {f_desc} |")
            md.append("\n")
    return "\n".join(md)


def convert_to_croissant(url, is_slice=False, traverse=False, reingest=False, user_name=None, user_email=None, index=False, elastic=False, expert="/expert/croissant", upload_gdrive=False, upload_gdrive_folder=None, translate=False, use_computer_vision=False):
    url = resolve_direct_url(url)
    direct_jsonld = check_dataverse_direct_export(url)
    if not direct_jsonld:
        direct_jsonld = check_dspace_direct_export(url)
        
    markdown_data = None
    dataverse_original_jsonld = None
    extracted_meta = {}

    if direct_jsonld:
        print("✓ Successfully retrieved Croissant JSON-LD directly from API!")
        direct_jsonld = fix_croissant_dataverse_distributions(direct_jsonld)
        markdown_data = generate_markdown_from_jsonld(direct_jsonld)
        dataverse_original_jsonld = direct_jsonld
        print("Generated Markdown representation of the JSON-LD.")

    page_meta = None
    sibling_pages = []
    
    if not markdown_data:
        result = fetch_url_markdown(url, traverse, use_computer_vision=use_computer_vision)
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
    import hashlib, base64
    def compute_unf6(content):
        words = sorted(content.split())
        c = b""
        for w in words:
            c += w.encode("utf-8") + b"\n\x00"
        d = hashlib.sha256(c).digest()[:16]
        raw_hash = base64.b64encode(d).decode("ascii")
        return raw_hash.replace("=", "").replace("+", "").replace("/", "")
        
    safe_name = compute_unf6(markdown_data)
        
    os.makedirs(os.path.join("data", "ca4eosc"), exist_ok=True)
    safe_name = os.path.join("data", "ca4eosc", safe_name)

    md_filename = f"{safe_name}.md"
    croissant_filename = os.path.basename(f"{safe_name}.jsonld")
    import requests
    citation_text = url
    if dataverse_original_jsonld:
        try:
            creators = dataverse_original_jsonld.get('creator', [])
            if isinstance(creators, dict): creators = [creators]
            author_str = ", ".join([c.get('name', '') for c in creators if isinstance(c, dict)])
            
            year = str(dataverse_original_jsonld.get('datePublished', ''))[:4]
            title = dataverse_original_jsonld.get('name', '')
            dataset_url = dataverse_original_jsonld.get('url', url)
            
            publisher = dataverse_original_jsonld.get('publisher', {})
            if isinstance(publisher, dict):
                pub_name = publisher.get('name', '')
            else:
                pub_name = str(publisher)
                
            version = dataverse_original_jsonld.get('version', '')
            version_str = f"V{version}" if str(version).replace('.','').isdigit() else str(version)
            
            citation_text = f'{author_str}, {year}, "{title}", {dataset_url}, {pub_name}, {version_str}'
            
            # Try to fetch UNF if persistentId is in URL
            if "persistentId=" in url:
                pid = url.split("persistentId=")[1].split("&")[0]
                base_url = url.split("/dataset.xhtml")[0]
                api_url = f"{base_url}/api/datasets/:persistentId?persistentId={pid}"
                res = requests.get(api_url, headers={'User-Agent': 'SemanticCroissant/1.0'})
                if res.status_code == 200:
                    data = res.json().get('data', {})
                    unf = data.get('latestVersion', {}).get('UNF', '')
                    if unf:
                        citation_text += f", {unf} [fileUNF]"
        except Exception:
            pass

    base_stem = os.path.basename(safe_name)
    extra_links = []
    try:
        minio_url_chk = os.environ.get("MINIO_URL", "http://minio:9000")
        _in_d = bool(os.environ.get("IN_DOCKER")) or os.path.exists("/.dockerenv")
        if _in_d and any(h in minio_url_chk for h in ["localhost", "127.0.0.1", "0.0.0.0"]):
            minio_url_chk = "http://minio:9000"
        from minio import Minio
        mc_c = Minio(minio_url_chk.replace("http://", "").replace("https://", "").rstrip("/"),
                     access_key=os.environ.get("MINIO_ROOT_USER", "minioadmin"),
                     secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin"),
                     secure=minio_url_chk.startswith("https"))
        for ext, label in [(".xlsx", "Spreadsheet (Excel)"), (".csv", "CSV Data"), (".jpg", "Original Image"), (".jpeg", "Original Image"), (".png", "Original Image")]:
            fn = f"{base_stem}{ext}"
            try:
                mc_c.stat_object("vault", fn)
                extra_links.append(f"* **{label}**: [{fn}](./{fn})")
            except Exception:
                pass
    except Exception:
        pass

    header = f"# Citation: {citation_text}\n\n* **Croissant Metadata**: [{croissant_filename}](./{croissant_filename})\n"
    if extra_links:
        header += "\n".join(extra_links) + "\n"
    header += "\n"
    
    # Don't duplicate if already present
    if not markdown_data.startswith(f"# Citation: {citation_text}"):
        markdown_data = header + markdown_data
        
    with open(md_filename, "w", encoding='utf-8') as f:
        f.write(markdown_data)
        
    print(f"Extracted markdown saved to {md_filename}")
    
    # Upload to Vault if MinIO is configured
    try:
        minio_url = os.environ.get("MINIO_URL", "http://minio:9000")
        _in_docker = bool(os.environ.get("IN_DOCKER")) or os.path.exists("/.dockerenv")
        if _in_docker and any(h in minio_url for h in ["localhost", "127.0.0.1", "0.0.0.0"]):
            minio_url = "http://minio:9000"
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
            
            # If any structured tables were parsed by PaleFire API, upload CSV and XLSX to MinIO vault
            # Supports single month or multiple months (e.g. July & August each in its own file)
            uploaded_table_stems = []
            if 'GLOBAL_PARSED_TABLES' in globals() and GLOBAL_PARSED_TABLES:
                try:
                    import pandas as pd
                    base_s = os.path.basename(safe_name)
                    num_tables = len(GLOBAL_PARSED_TABLES)

                    for t_idx, item in enumerate(GLOBAL_PARSED_TABLES):
                        if isinstance(item, dict):
                            df_tbl = item['df']
                            m_lbl = item.get('month_name', '').lower()
                            t_stem = f"{base_s}_{m_lbl}" if (num_tables > 1 and m_lbl) else (f"{base_s}_{t_idx+1}" if num_tables > 1 else base_s)
                            sheet_title = item.get('month_name') or 'Rainfall Measurements'
                        else:
                            df_tbl = item
                            t_stem = f"{base_s}_{t_idx+1}" if num_tables > 1 else base_s
                            sheet_title = 'Rainfall Measurements'

                        uploaded_table_stems.append((t_stem, sheet_title))

                        # Add GeoID column from location columns if not already present
                        if 'GeoID' not in df_tbl.columns and any(c in df_tbl.columns for c in ('Community', 'Municipality', 'Department', 'Country')):
                            try:
                                import requests as _req_geo
                                _loc_cache = {}
                                def _lookup_geoid(row):
                                    parts = [str(row.get(c, '')).strip() for c in ('Community', 'Municipality', 'Department', 'Country') if c in df_tbl.columns]
                                    parts = [p for p in parts if p and p.lower() not in ('n/a', 'none', 'nan', 'unknown')]
                                    q = ', '.join(parts)
                                    if not q:
                                        return ''
                                    if q in _loc_cache:
                                        return _loc_cache[q]
                                    try:
                                        gr = _req_geo.get('https://nominatim.openstreetmap.org/search', params={'q': q, 'format': 'json', 'limit': 1}, headers={'User-Agent': 'semantic-croissant/1.0'}, timeout=5)
                                        if gr.status_code == 200 and gr.json():
                                            gid = str(gr.json()[0].get('osm_id', ''))
                                            _loc_cache[q] = gid
                                            return gid
                                    except Exception:
                                        pass
                                    _loc_cache[q] = ''
                                    return ''
                                df_tbl['GeoID'] = df_tbl.apply(_lookup_geoid, axis=1)
                            except Exception:
                                pass

                        # Upload CSV
                        csv_b = df_tbl.to_csv(index=False).encode('utf-8')
                        client.put_object("vault", f"{t_stem}.csv", io.BytesIO(csv_b), len(csv_b), content_type="text/csv")
                        
                        # Upload XLSX
                        xl_buf = io.BytesIO()
                        with pd.ExcelWriter(xl_buf, engine='openpyxl') as wr:
                            df_tbl.to_excel(wr, sheet_name=sheet_title[:31], index=False)
                        xl_b = xl_buf.getvalue()
                        client.put_object("vault", f"{t_stem}.xlsx", io.BytesIO(xl_b), len(xl_b), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                        print(f"Uploaded parsed table {t_stem}.csv and {t_stem}.xlsx to vault ({sheet_title}).")

                    # Also keep primary base_s.csv and base_s.xlsx pointing to the latest/first table for backward compatibility
                    if num_tables > 1:
                        primary_df = GLOBAL_PARSED_TABLES[-1]['df'] if isinstance(GLOBAL_PARSED_TABLES[-1], dict) else GLOBAL_PARSED_TABLES[-1]
                        csv_b_main = primary_df.to_csv(index=False).encode('utf-8')
                        client.put_object("vault", f"{base_s}.csv", io.BytesIO(csv_b_main), len(csv_b_main), content_type="text/csv")
                        xl_buf_main = io.BytesIO()
                        with pd.ExcelWriter(xl_buf_main, engine='openpyxl') as wr:
                            primary_df.to_excel(wr, sheet_name='Rainfall Measurements', index=False)
                        xl_b_main = xl_buf_main.getvalue()
                        client.put_object("vault", f"{base_s}.xlsx", io.BytesIO(xl_b_main), len(xl_b_main), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                except Exception as e_up_tbl:
                    print(f"Warning: Failed to upload parsed tables: {e_up_tbl}")

            if 'GLOBAL_HTML_CV_IMAGES' in globals() and globals()['GLOBAL_HTML_CV_IMAGES']:
                try:
                    base_s = os.path.basename(safe_name)
                    uploaded_cv_imgs = []
                    for idx, (orig_img_url, img_bytes, ctype) in enumerate(globals()['GLOBAL_HTML_CV_IMAGES'], 1):
                        ext = os.path.splitext(orig_img_url.split("?")[0])[1].lower() or ".jpg"
                        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                            ext = ".jpg"
                        img_fname = f"{base_s}_image_{idx}{ext}"
                        client.put_object("vault", img_fname, io.BytesIO(img_bytes), len(img_bytes), content_type=ctype)
                        uploaded_cv_imgs.append((img_fname, ctype, orig_img_url))
                        print(f"Uploaded HTML CV image {img_fname} to vault.")
                    globals()['GLOBAL_HTML_CV_UPLOADED_IMAGES'] = uploaded_cv_imgs
                except Exception as e_cv_up:
                    print(f"Warning: Failed to upload HTML CV images: {e_cv_up}")

            if 'GLOBAL_GITHUB_RAW_README' in globals() and globals()['GLOBAL_GITHUB_RAW_README']:
                try:
                    _rm_bytes = globals()['GLOBAL_GITHUB_RAW_README']
                    _rm_fn = f"{os.path.basename(safe_name)}_README.md"
                    client.put_object("vault", _rm_fn, io.BytesIO(_rm_bytes), len(_rm_bytes), content_type="text/markdown")
                    globals()['GLOBAL_GITHUB_README_FILE'] = _rm_fn
                    print(f"Uploaded raw GitHub README.md as {_rm_fn} to vault.")
                except Exception as e_rm_up:
                    print(f"Warning: Failed to upload raw GitHub README.md: {e_rm_up}")

            if 'GLOBAL_YOUTUBE_README' in globals() and globals()['GLOBAL_YOUTUBE_README']:
                try:
                    _ytr_b = globals()['GLOBAL_YOUTUBE_README']
                    _ytr_fn = f"{os.path.basename(safe_name)}_README.md"
                    client.put_object("vault", _ytr_fn, io.BytesIO(_ytr_b), len(_ytr_b), content_type="text/markdown")
                    globals()['GLOBAL_YOUTUBE_README_FILE'] = _ytr_fn
                except Exception as e_ytr:
                    print(f"Warning: Failed to upload YouTube README.md: {e_ytr}")
            if 'GLOBAL_YOUTUBE_AGENTS' in globals() and globals()['GLOBAL_YOUTUBE_AGENTS']:
                try:
                    _yta_b = globals()['GLOBAL_YOUTUBE_AGENTS']
                    _yta_fn = f"{os.path.basename(safe_name)}_Agents.md"
                    client.put_object("vault", _yta_fn, io.BytesIO(_yta_b), len(_yta_b), content_type="text/markdown")
                    globals()['GLOBAL_YOUTUBE_AGENTS_FILE'] = _yta_fn
                except Exception as e_yta:
                    print(f"Warning: Failed to upload YouTube Agents.md: {e_yta}")
                    print(f"Warning: Failed to upload parsed tables to vault: {e_up_tbl}")

            # If PDF assets (page renders and embedded images) were generated, upload them to MinIO vault
            if 'GLOBAL_PDF_ASSETS' in globals() and GLOBAL_PDF_ASSETS:
                try:
                    base_s = os.path.basename(safe_name)
                    print(f"Uploading {len(GLOBAL_PDF_ASSETS)} PDF page renders & images to MinIO vault...")
                    for asset in GLOBAL_PDF_ASSETS:
                        asset_fn = f"{base_s}{asset['filename_suffix']}"
                        asset_bytes = asset['bytes']
                        if asset_bytes:
                            client.put_object(
                                "vault",
                                asset_fn,
                                io.BytesIO(asset_bytes),
                                len(asset_bytes),
                                content_type=asset.get("mimetype", "image/jpeg")
                            )
                    print("Finished uploading PDF assets to MinIO vault.")
                except Exception as e_pdf_assets:
                    print(f"Warning: Failed to upload PDF assets to vault: {e_pdf_assets}")

            base_vault_url = f"{get_base_host()}/vault"
            # If the original input is a local file (e.g. image, csv, pdf), upload it first so it is present in vault
            if os.path.isfile(url):
                orig_ext = os.path.splitext(url)[1]
                orig_vault_name = f"{os.path.basename(safe_name)}{orig_ext}"
                try:
                    with open(url, "rb") as f_orig:
                        orig_bytes = f_orig.read()
                    import mimetypes
                    guessed_mime, _ = mimetypes.guess_type(url)
                    orig_mime = guessed_mime or "application/octet-stream"
                    client.put_object(
                        "vault",
                        orig_vault_name,
                        data=io.BytesIO(orig_bytes),
                        length=len(orig_bytes),
                        content_type=orig_mime
                    )
                    print(f"Original source file successfully uploaded to vault: {base_vault_url}/{orig_vault_name}")
                except Exception as e_orig_up:
                    print(f"Warning: Failed to upload original file to MinIO vault: {e_orig_up}")

            # Re-generate markdown header with spreadsheet links now that files are in vault
            base_stem = os.path.basename(safe_name)
            extra_links = []
            # Check all uploaded table files
            for t_stem, s_title in uploaded_table_stems:
                lbl_suffix = f" ({s_title})" if s_title and s_title != 'Rainfall Measurements' else ""
                fn_xl = f"{t_stem}.xlsx"
                fn_csv = f"{t_stem}.csv"
                try:
                    client.stat_object("vault", fn_xl)
                    extra_links.append(f"* **Spreadsheet (Excel){lbl_suffix}**: [{fn_xl}](./{fn_xl})")
                except Exception:
                    pass
                try:
                    client.stat_object("vault", fn_csv)
                    extra_links.append(f"* **CSV Data{lbl_suffix}**: [{fn_csv}](./{fn_csv})")
                except Exception:
                    pass

            for ext, label in [(".jpg", "Original Image"), (".jpeg", "Original Image"), (".png", "Original Image")]:
                fn = f"{base_stem}{ext}"
                try:
                    client.stat_object("vault", fn)
                    extra_links.append(f"* **{label}**: [{fn}](./{fn})")
                except Exception:
                    pass

            # Upload datamaps CSVs early if datamaps pipeline ran so header links are guaranteed to work
            try:
                import sys as _sys
                _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import datamaps_runner
                dm_res_early = datamaps_runner.RESULTS.get(resolve_direct_url(url)) or datamaps_runner.RESULTS.get(url)
                if dm_res_early:
                    datamaps_runner.upload_and_distributions(dm_res_early, client, get_base_host(), doc_id=base_stem)
                    fn_dm_csv = f"{base_stem}.csv"
                    if not any(fn_dm_csv in l for l in extra_links):
                        extra_links.append(f"* **Master CSV Data (Heatmap Report)**: [{fn_dm_csv}](./{fn_dm_csv})")
                    maps_list = dm_res_early.get("maps", [])
                    if maps_list:
                        extra_links.append("\n## Extracted Map Datasets (Two Maps Per Page: Left & Right Panels)\n")
                        extra_links.append("| Page | Panel | Map Variable / Title | CSV Dataset | JSON-LD Observations |")
                        extra_links.append("|---|---|---|---|---|")
                        for m_item in maps_list:
                            p_num = m_item.get("page") or 0
                            s_side = m_item.get("side") or "single"
                            m_title = (m_item.get("title") or f"Page {p_num} {s_side}").replace("|", "/")
                            c_fn = f"{base_stem}_page_{p_num:02d}_{s_side}.csv"
                            j_fn = f"{base_stem}_page_{p_num:02d}_{s_side}.jsonld"
                            extra_links.append(f"| Page {p_num:02d} | `{s_side}` | {m_title} | [{c_fn}](./{c_fn}) | [{j_fn}](./{j_fn}) |")
            except Exception as e_dm_early:
                print(f"Warning: Early datamaps upload failed: {e_dm_early}")

            if extra_links:
                clean_header = f"# Citation: {citation_text}\n\n* **Croissant Metadata**: [{croissant_filename}](./{croissant_filename})\n" + "\n".join(extra_links) + "\n\n"
                # Strip old citation header if present
                if markdown_data.startswith(f"# Citation: {citation_text}"):
                    parts = markdown_data.split("\n\n", 2)
                    body_start = parts[2] if len(parts) > 2 else markdown_data
                    markdown_data = clean_header + body_start

            vault_filename = os.path.basename(md_filename)
            md_bytes = markdown_data.encode('utf-8')
            client.put_object(
                "vault",
                vault_filename,
                data=io.BytesIO(md_bytes),
                length=len(md_bytes),
                content_type="text/markdown"
            )
            # If PDF assets (page renders and embedded images) were generated, upload them to MinIO vault
            if 'GLOBAL_PDF_ASSETS' in globals() and GLOBAL_PDF_ASSETS:
                try:
                    base_s = os.path.basename(safe_name)
                    print(f"Uploading {len(GLOBAL_PDF_ASSETS)} PDF page renders & images to MinIO vault...")
                    for asset in GLOBAL_PDF_ASSETS:
                        asset_fn = f"{base_s}{asset['filename_suffix']}"
                        asset_bytes = asset['bytes']
                        if asset_bytes:
                            client.put_object(
                                "vault",
                                asset_fn,
                                io.BytesIO(asset_bytes),
                                len(asset_bytes),
                                content_type=asset.get("mimetype", "image/jpeg")
                            )
                    print("Finished uploading PDF assets to MinIO vault.")
                except Exception as e_pdf_assets:
                    print(f"Warning: Failed to upload PDF assets to vault: {e_pdf_assets}")

            base_vault_url = f"{get_base_host()}/vault"
            print(f"Extracted markdown successfully uploaded to vault: {base_vault_url}/{vault_filename}")

# Original file upload moved before header generation
    except Exception as e:
        print(f"Warning: Failed to upload markdown to MinIO vault: {e}")

    try:
        from langdetect import detect
        lang = detect(markdown_data)
        print(f"Detected language: {lang}")
    except Exception as e:
        print(f"Language detection failed: {e}")

    original_md_filename = md_filename
    if translate and lang != "en":
        translated_md = translate_to_english(markdown_data)
        if translated_md and translated_md != markdown_data:
            markdown_data = translated_md
            md_filename = f"{safe_name}_en_content.md"
            with open(md_filename, "w", encoding='utf-8') as f:
                f.write(markdown_data)
            print(f"Translated markdown saved to {md_filename}")
            try:

                vault_en_filename = os.path.basename(md_filename)
                en_bytes = markdown_data.encode('utf-8')
                client.put_object(
                    "vault",
                    vault_en_filename,
                    data=io.BytesIO(en_bytes),
                    length=len(en_bytes),
                    content_type="text/markdown"
                )
                print(f"Translated markdown successfully uploaded to vault: {get_base_host()}/vault/{vault_en_filename}")
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
                res_chunk = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload_chunk, headers=OLLAMA_HEADERS, timeout=600)
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
                res_ingest = requests.post(f"{OLLAMA_HOST}/api/generate", json=ingest_payload, headers=OLLAMA_HEADERS, timeout=120)
                res_ingest.raise_for_status()
                print(f"Ollama ingestion response: {res_ingest.json().get('response', '').strip()}")
            except Exception as e:
                print(f"Failed to send chunk {i} to Ollama: {e}")

    if dataverse_original_jsonld:
        print(f"\n--- Skipping LLM extraction; using direct Dataverse JSON-LD for {url} ---")
    else:
        print(f"\n--- Processing {url} using {MODEL_NAME} ---")
        
        # Truncate to first 5,000 characters to prevent context window overflow which causes hallucinated JSON
        llm_context_data = markdown_data
        if len(llm_context_data) > 5000:
            print(f"Warning: Markdown is too large ({len(llm_context_data)} chars). Truncating to 5,000 chars.")
            llm_context_data = llm_context_data[:5000]

        prompt = f"Create Croissant JSON-LD metadata for a machine learning model or dataset. The source URL is {url}."
        if lang != 'en':
            prompt += f" The source documentation is in language code '{lang}'. Please do a precise ONE-to-ONE translation of the relevant metadata to English and output the Croissant JSON-LD entirely in English."
        
        # Integrate Computer Vision Croissant knowledge layer if available
        if extracted_meta and extracted_meta.get("initial_croissant"):
            import json as _json_layer
            initial_cr = extracted_meta.get("initial_croissant")
            prompt += f"\n\n[Computer Vision Knowledge Layer]: Prior analysis with multimodal visual model produced this initial Croissant metadata layer:\n{_json_layer.dumps(initial_cr, indent=2)}\nUse this knowledge layer along with OCR and text content below to produce an integrated, authoritative Croissant JSON-LD metadata.\n"

        prompt += f" Here is the documentation and description extracted from its official page:\n\n{llm_context_data}\n\n"
        prompt += "Extract relevant information such as the description, authors, license, keywords, tags, or any dataset dependencies into the Croissant metadata if available. Map keywords/tags to the standard schema:keywords property, and extract them EXACTLY as they appear in the text (do not change casing or invent new tags). Ensure 'keywords' is formatted as a JSON array of strings, not a single comma-separated string. IMPORTANT: For any fields or data that do not have a standard mapping in Croissant, include them in the JSON-LD under a custom field called 'unmappedFields' as a list of key-value pairs.\n"
        prompt += 'Example structure:\n{\n  "@context": {\n    "@vocab": "http://schema.org/",\n    "sc": "http://schema.org/",\n    "schema": "http://schema.org/",\n    "cr": "http://mlcommons.org/croissant/",\n    "dct": "http://purl.org/dc/terms/",\n    "conformsTo": "dct:conformsTo",\n    "distribution": {"@id": "cr:distribution"},\n    "bs4ExtractionPattern": {"@id": "sc:processingRequirement", "@type": "@json"},\n    "unf": "https://guides.dataverse.org/en/6.9/developers/unf/unf-v6.html",\n    "odrl": "http://www.w3.org/ns/odrl/2/",\n    "cdif": "https://cdif.org/1.1/",\n    "did": "https://www.w3.org/ns/did/v1",\n    "url": {"@type": "http://www.w3.org/2001/XMLSchema#string"}\n  },\n  "@type": "sc:SoftwareApplication",\n  "name": "...",\n  "description": "...",\n  "url": "...",\n  "license": "...",\n  "keywords": [],\n  "unmappedFields": [],\n  "contentUrl": "...",\n  "isBasedOn": [],\n  "isPartOf": [{"@type": "Collection", "name": "/expert/croissant"}],\n  "version": "1.0",\n  "creator": {"@type": "Person", "name": "...", "email": "..."}\n}\n\n'
        prompt += "CRITICAL: Do NOT invent, hallucinate, or generate generic information. You MUST extract the name, description, and details directly from the provided text above.\n\nOutput ONLY a valid JSON object."
        
    start_time = time.time()
    try:
        MAX_RETRIES = 1 if dataverse_original_jsonld else 3
        for attempt in range(1, MAX_RETRIES + 1):
            if dataverse_original_jsonld:
                output = json.dumps(dataverse_original_jsonld)
            else:
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
                        "num_ctx": 8192
                    }
                }
                
                response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, headers=OLLAMA_HEADERS, timeout=600)
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
                if isinstance(json_data, list):
                    json_data = json_data[0] if json_data else {}
                print("✓ JSON is well-formed")
                
                # Inject link to the generated markdown file(s)
                original_vault_url = f"{get_base_host()}/vault/{os.path.basename(original_md_filename)}"
                doc_links = [{
                    "@type": "CreativeWork",
                    "name": "Scraped Markdown Content",
                    "contentUrl": original_vault_url,
                    "encodingFormat": "text/markdown"
                }]
                
                if original_md_filename != md_filename:
                    translated_vault_url = f"{get_base_host()}/vault/{os.path.basename(md_filename)}"
                    doc_links.append({
                        "@type": "CreativeWork",
                        "name": "Translated Markdown Content (English)",
                        "contentUrl": translated_vault_url,
                        "encodingFormat": "text/markdown",
                        "creator": {
                            "@type": "SoftwareApplication",
                            "name": os.environ.get("MODEL") or os.environ.get("MODEL_NAME") or os.environ.get("OLLAMA_DEFAULT_MODEL", os.environ.get("OLLAMA_DEFAULT_MODEL", "gemma4:e2b")),
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
                            "contentUrl": f"{get_base_host()}/vault/{os.path.basename(sib_md_filename)}",
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
                    
                # Always ensure canonical direct URL
                canonical_direct = (page_meta or {}).get("canonicalUrl") or url
                json_data["url"] = canonical_direct
                json_data["contentUrl"] = canonical_direct
                    
                if dataverse_original_jsonld:
                    json_data["isBasedOn"].append({
                        "@type": "sc:Dataset",
                        "name": dataverse_original_jsonld.get("name", "Original Dataverse Dataset"),
                        "url": url,
                        "description": "The original source JSON-LD metadata fetched from Dataverse."
                    })
                    
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
                
                # Force a standard robust Croissant context instead of trusting the LLM
                json_data.pop("@context", None)
                ordered_data["@context"] = {
                    "@vocab": "http://schema.org/",
                    "sc": "http://schema.org/",
                    "schema": "http://schema.org/",
                    "cr": "http://mlcommons.org/croissant/",
                    "odrl": "http://www.w3.org/ns/odrl/2/",
                    "dc": "http://purl.org/dc/terms/",
                    "dct": "http://purl.org/dc/terms/",
                    "conformsTo": "dct:conformsTo",
                    "distribution": {"@id": "cr:distribution"},
                    "unf": "https://guides.dataverse.org/en/6.9/developers/unf/unf-v6.html",
                    "cdif": "https://cdif.org/1.1/",
                    "did": "https://www.w3.org/ns/did/v1",
                    "url": {"@type": "http://www.w3.org/2001/XMLSchema#string"}
                }
                ordered_data["@type"] = json_data.pop("@type", "Dataset")
                json_data.pop("@context", None)
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


        # Attach extracted Markdown (.md) as a cr:FileObject in distribution
        try:
            _md_fn = f"{os.path.basename(safe_name)}.md"
            _bhost = get_base_host().rstrip("/")
            _was_str = isinstance(output, str)
            _out_obj = json.loads(output) if _was_str else output
            if isinstance(_out_obj, dict):
                _cur_d = _out_obj.get("distribution", [])
                if not isinstance(_cur_d, list):
                    _cur_d = [_cur_d] if _cur_d else []
                if not any(isinstance(d, dict) and (d.get("@id") == _md_fn or d.get("name") == _md_fn) for d in _cur_d):
                    _cur_d.append({
                        "@type": "cr:FileObject",
                        "@id": _md_fn,
                        "name": _md_fn,
                        "description": "Extracted Markdown content",
                        "contentUrl": f"{_bhost}/vault/{_md_fn}",
                        "encodingFormat": "text/markdown",
                    })
                    _out_obj["distribution"] = _cur_d
                    if 'GLOBAL_GITHUB_README_FILE' in globals() and globals()['GLOBAL_GITHUB_README_FILE']:
                        _rm_fn = globals()['GLOBAL_GITHUB_README_FILE']
                        if not any(isinstance(d, dict) and d.get("@id") == _rm_fn for d in _cur_d):
                            _cur_d.append({
                                "@type": "cr:FileObject",
                                "@id": _rm_fn,
                                "name": "README.md",
                                "description": "Original GitHub README.md",
                                "contentUrl": f"{_bhost}/vault/{_rm_fn}",
                                "encodingFormat": "text/markdown",
                            })
                            _out_obj["distribution"] = _cur_d
                    for _gkey, _dname, _ddesc in (
                        ("GLOBAL_YOUTUBE_README_FILE", "README.md", "YouTube video metadata and description"),
                        ("GLOBAL_YOUTUBE_AGENTS_FILE", "Agents.md", "YouTube video transcript"),
                    ):
                        if _gkey in globals() and globals()[_gkey]:
                            _yfn = globals()[_gkey]
                            if not any(isinstance(d, dict) and d.get("@id") == _yfn for d in _cur_d):
                                _cur_d.append({
                                    "@type": "cr:FileObject",
                                    "@id": _yfn,
                                    "name": _dname,
                                    "description": _ddesc,
                                    "contentUrl": f"{_bhost}/vault/{_yfn}",
                                    "encodingFormat": "text/markdown",
                                })
                                _out_obj["distribution"] = _cur_d
                    if _was_str:
                        output = json.dumps(_out_obj, indent=2)
        except Exception as e_md_d:
            print(f"Warning: Failed to attach Markdown distribution: {e_md_d}")

        # Attach HTML CV images as distributions if uploaded
        if 'GLOBAL_HTML_CV_UPLOADED_IMAGES' in globals() and globals()['GLOBAL_HTML_CV_UPLOADED_IMAGES']:
            try:
                _cv_dists = []
                _bhost = get_base_host().rstrip("/")
                for _fn, _ct, _orig in globals()['GLOBAL_HTML_CV_UPLOADED_IMAGES']:
                    _cv_dists.append({
                        "@type": "cr:FileObject",
                        "@id": _fn,
                        "name": _fn,
                        "description": f"Extracted image from {_orig}",
                        "contentUrl": f"{_bhost}/vault/{_fn}",
                        "encodingFormat": _ct,
                    })
                if isinstance(output, dict):
                    _cur_d = output.get("distribution", [])
                    if not isinstance(_cur_d, list):
                        _cur_d = [_cur_d] if _cur_d else []
                    _cur_d.extend(_cv_dists)
                    output["distribution"] = _cur_d
            except Exception as e_cv_d:
                print(f"Warning: Failed to attach HTML CV image distributions: {e_cv_d}")

        # Attach datamaps outputs (CSV + JSON-LD) as distributions, uploaded to the vault
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import datamaps_runner
            dm_result = datamaps_runner.RESULTS.get(resolve_direct_url(url)) or datamaps_runner.RESULTS.get(url)
            if dm_result:
                dm_client = None
                try:
                    from minio import Minio
                    _murl = os.environ.get("MINIO_URL", "http://minio:9000")
                    _in_d_dm = bool(os.environ.get("IN_DOCKER")) or os.path.exists("/.dockerenv")
                    if _in_d_dm and any(h in _murl for h in ["localhost", "127.0.0.1", "0.0.0.0"]):
                        _murl = "http://minio:9000"
                    dm_client = Minio(_murl.replace("http://", "").replace("https://", "").rstrip("/"),
                                      access_key=os.environ.get("MINIO_ROOT_USER", "minioadmin"),
                                      secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin"),
                                      secure=_murl.startswith("https"))
                except Exception as e_mc:
                    print(f"Warning: MinIO unavailable for datamaps upload: {e_mc}")
                dm_dists = datamaps_runner.upload_and_distributions(dm_result, dm_client, get_base_host(), doc_id=os.path.basename(safe_name))
                output = datamaps_runner.inject_distributions(output, dm_dists)
                print(f"Added {len(dm_dists)} datamaps distributions to Croissant.")
        except ImportError:
            pass
        except Exception as e_dm:
            print(f"Warning: failed to attach datamaps distributions: {e_dm}")

        # If spreadsheet/csv files exist in MinIO vault (e.g. generated for rainfall observation sheets), attach them as distributions
        try:
            extra_dists = []
            minio_url_check = os.environ.get("MINIO_URL", "http://minio:9000")
            _in_dock = bool(os.environ.get("IN_DOCKER")) or os.path.exists("/.dockerenv")
            if _in_dock and any(h in minio_url_check for h in ["localhost", "127.0.0.1", "0.0.0.0"]):
                minio_url_check = "http://minio:9000"
            _ep = minio_url_check.replace("http://", "").replace("https://", "").rstrip("/")
            from minio import Minio
            mc_check = Minio(_ep, access_key=os.environ.get("MINIO_ROOT_USER", "minioadmin"),
                             secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin"),
                             secure=minio_url_check.startswith("https"))
            base_safe = os.path.basename(safe_name)
            # Find all uploaded files for this dataset in the vault (e.g. base_safe_july.xlsx, base_safe_august.csv, etc.)
            check_targets = [
                (f"{base_safe}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Spreadsheet of daily measurements"),
                (f"{base_safe}.csv", "text/csv", "CSV dataset of daily measurements")
            ]
            if 'uploaded_table_stems' in locals() and uploaded_table_stems:
                for t_st, s_tit in uploaded_table_stems:
                    if t_st != base_safe:
                        check_targets.append((f"{t_st}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"Spreadsheet of daily measurements ({s_tit})"))
                        check_targets.append((f"{t_st}.csv", "text/csv", f"CSV dataset of daily measurements ({s_tit})"))

            for obj_name, mime, desc in check_targets:
                try:
                    stat = mc_check.stat_object("vault", obj_name)
                    import hashlib
                    obj_bytes = mc_check.get_object("vault", obj_name).read()
                    extra_dists.append({
                        "@type": "cr:FileObject",
                        "@id": obj_name,
                        "name": obj_name,
                        "description": desc,
                        "contentUrl": f"{get_base_host()}/vault/{obj_name}",
                        "encodingFormat": mime,
                        "contentSize": f"{stat.size} B",
                        "sha256": hashlib.sha256(obj_bytes).hexdigest()
                    })
                except Exception:
                    pass
            if extra_dists:
                try:
                    j_obj = json.loads(output)
                    tgt = j_obj[0] if isinstance(j_obj, list) and j_obj else j_obj
                    if isinstance(tgt, dict):
                        existing_dist = tgt.get("distribution") or []
                        if isinstance(existing_dist, dict):
                            existing_dist = [existing_dist]
                        for ed in extra_dists:
                            if not any(d.get("@id") == ed["@id"] for d in existing_dist if isinstance(d, dict)):
                                existing_dist.append(ed)
                        tgt["distribution"] = existing_dist
                        output = json.dumps(j_obj, indent=2, ensure_ascii=False)
                        print(f"Added {len(extra_dists)} spreadsheet distributions to Croissant.")
                except Exception as e_ed:
                    print(f"Warning: Failed to inject extra spreadsheet distributions: {e_ed}")
        except Exception as e_mc_chk:
            pass

        # Attach original file as distribution if local file was processed
        if os.path.isfile(url):
            try:
                orig_ext = os.path.splitext(url)[1]
                orig_vault_name = f"{os.path.basename(safe_name)}{orig_ext}"
                orig_size = os.path.getsize(url)
                import mimetypes, hashlib
                guessed_mime, _ = mimetypes.guess_type(url)
                orig_mime = guessed_mime or "application/octet-stream"
                with open(url, "rb") as f_hash:
                    orig_sha256 = hashlib.sha256(f_hash.read()).hexdigest()

                orig_dist = [{
                    "@type": "cr:FileObject",
                    "@id": orig_vault_name,
                    "name": os.path.basename(url),
                    "description": f"Original source file ({os.path.basename(url)})",
                    "contentUrl": f"{get_base_host()}/vault/{orig_vault_name}",
                    "encodingFormat": orig_mime,
                    "contentSize": f"{orig_size} B",
                    "sha256": orig_sha256
                }]
                try:
                    j_obj = json.loads(output)
                    tgt = j_obj[0] if isinstance(j_obj, list) and j_obj else j_obj
                    if isinstance(tgt, dict):
                        existing_dist = tgt.get("distribution") or []
                        if isinstance(existing_dist, dict):
                            existing_dist = [existing_dist]
                        # Don't duplicate if already present
                        if not any(d.get("@id") == orig_vault_name or d.get("contentUrl") == f"{get_base_host()}/vault/{orig_vault_name}" for d in existing_dist if isinstance(d, dict)):
                            tgt["distribution"] = existing_dist + orig_dist
                            output = json.dumps(j_obj, indent=2, ensure_ascii=False)
                            print(f"Added original file {orig_vault_name} to Croissant distribution.")
                except Exception as e_dist:
                    print(f"Warning: Failed to inject original file distribution: {e_dist}")
            except Exception as e_att:
                print(f"Warning: Failed to prepare original file distribution: {e_att}")

        # Attach PDF page renders and extracted images as distributions
        if 'GLOBAL_PDF_ASSETS' in globals() and GLOBAL_PDF_ASSETS:
            try:
                base_safe = os.path.basename(safe_name)
                pdf_dists = []
                import hashlib
                for asset in GLOBAL_PDF_ASSETS:
                    asset_fn = f"{base_safe}{asset['filename_suffix']}"
                    asset_bytes = asset.get('bytes')
                    if asset_bytes:
                        pdf_dists.append({
                            "@type": "cr:FileObject",
                            "@id": asset_fn,
                            "name": asset_fn,
                            "description": asset.get("description") or f"PDF Resource ({asset_fn})",
                            "contentUrl": f"{get_base_host()}/vault/{asset_fn}",
                            "encodingFormat": asset.get("mimetype", "image/jpeg"),
                            "contentSize": f"{len(asset_bytes)} B",
                            "sha256": hashlib.sha256(asset_bytes).hexdigest()
                        })
                if pdf_dists:
                    try:
                        j_obj = json.loads(output)
                        tgt = j_obj[0] if isinstance(j_obj, list) and j_obj else j_obj
                        if isinstance(tgt, dict):
                            existing_dist = tgt.get("distribution") or []
                            if isinstance(existing_dist, dict):
                                existing_dist = [existing_dist]
                            for pd_dist in pdf_dists:
                                if not any(d.get("@id") == pd_dist["@id"] for d in existing_dist if isinstance(d, dict)):
                                    existing_dist.append(pd_dist)
                            tgt["distribution"] = existing_dist
                            output = json.dumps(j_obj, indent=2, ensure_ascii=False)
                            print(f"Added {len(pdf_dists)} PDF page renders & extracted image distributions to Croissant.")
                    except Exception as e_pdf_inj:
                        print(f"Warning: Failed to inject PDF distributions: {e_pdf_inj}")
            except Exception as e_pdf_chk:
                pass

        output_filename = f"{safe_name}_croissant.jsonld"
        
        with open(output_filename, "w", encoding='utf-8') as f:
            f.write(output)
        print(f"\nOutput saved to {output_filename}")
        
        # Upload to Vault if MinIO is configured
        try:
            minio_url = os.environ.get("MINIO_URL", "http://minio:9000")
            _in_docker = bool(os.environ.get("IN_DOCKER")) or os.path.exists("/.dockerenv")
            if _in_docker and any(h in minio_url for h in ["localhost", "127.0.0.1", "0.0.0.0"]):
                minio_url = "http://minio:9000"
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
                
                # Upload JSON-LD
                vault_jsonld_filename = croissant_filename
                jsonld_bytes = output.encode('utf-8')
                client.put_object(
                    "vault",
                    vault_jsonld_filename,
                    data=io.BytesIO(jsonld_bytes),
                    length=len(jsonld_bytes),
                    content_type="application/ld+json"
                )
                print(f"Croissant JSON-LD successfully uploaded to vault: {get_base_host()}/vault/{vault_jsonld_filename}")
                
                # Generate and upload Datacard
                datacard_filename = vault_jsonld_filename.replace(".jsonld", "_datacard.md")
                datacard_content = f"**Original Source:** [View URL]({url})\n\n"
                datacard_content += f"**Markdown Document:** [View Extracted Markdown]({get_base_host()}/vault/{os.path.basename(md_filename)})\n\n"
                datacard_content += f"**Metadata:** [View Croissant JSON-LD Data]({get_base_host()}/vault/{vault_jsonld_filename})\n\n"
                import hashlib
                datacard_content += f"---\n**Digital Signature:** `{hashlib.sha256(jsonld_bytes).hexdigest()}`\n"
                
                dc_bytes = datacard_content.encode('utf-8')
                client.put_object(
                    "vault",
                    datacard_filename,
                    data=io.BytesIO(dc_bytes),
                    length=len(dc_bytes),
                    content_type="text/markdown"
                )
                print(f"Datacard successfully uploaded to vault: {get_base_host()}/vault/{datacard_filename}")
        except Exception as e:
            print(f"Warning: Failed to upload JSON-LD/Datacard to MinIO vault: {e}")
        
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
                res_index = requests.post(f"{OLLAMA_HOST}/api/generate", json=index_payload, headers=OLLAMA_HEADERS, timeout=600)
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

def process_spreadsheet(url, is_slice=False, traverse=False, reingest=False, user_name=None, user_email=None, index=False, elastic=False, expert="/expert/croissant", upload_gdrive=False, upload_gdrive_folder=None, translate=False):
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
            executor.submit(convert_to_croissant, target_url, is_slice, traverse, reingest, user_name, user_email, index, elastic, expert, upload_gdrive, upload_gdrive_folder, translate): target_url
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
    parser.add_argument("--translate", action="store_true", help="Automatically translate content to English if in another language")
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
    parser.add_argument("--computer-vision", "--cv", action="store_true", help="Use Computer Vision to extract charts, maps, and tables from PDFs")
    parser.add_argument("--host", type=str, help="Base host URL or domain (e.g. https://ai.mediaquantum.eu or ai.mediaquantum.eu)")
    parser.add_argument("--engine", type=str, help="OCR engine(s) to use in PaleFire ImageParser, e.g. ['tesseract', 'ollama_gemma4:31b-cloud', 'microsoft_trocr']")
    parser.add_argument("--ollama-visual-model", type=str, help="Ollama visual model (e.g. gemma4:31b, gemma4:31b-cloud)")
    args = parser.parse_args()
    
    if args.host:
        h = args.host.strip()
        if not h.startswith("http://") and not h.startswith("https://"):
            if h.startswith("localhost") or h.startswith("127.0.0.1") or (":" in h and h.split(":")[0].replace(".", "").isdigit()):
                h = f"http://{h}"
            else:
                h = f"https://{h}"
        os.environ["HOST"] = h
        os.environ["MCP_DOMAIN"] = h.replace("http://", "").replace("https://", "").split("/")[0]
    
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
        DOC_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.tiff', '.bmp', '.csv', '.tsv', '.xlsx', '.xls', '.ods', '.pdf', '.docx', '.doc')
        if getattr(args, "format", "croissant") == "oai":
            process_local_file(args.url, args)
            import sys
            sys.exit(0)
        elif args.url.lower().endswith(DOC_EXTS):
            convert_to_croissant(args.url, args.slice, args.traverse, args.reingest, args.user_name, args.user_email, args.index_ollama, args.elastic, args.expert, getattr(args, "upload_gdrive", False), getattr(args, "upload_gdrive_folder", None), getattr(args, "translate", False), getattr(args, "computer_vision", False))
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
                convert_to_croissant(target_url, args.slice, args.traverse, args.reingest, args.user_name, args.user_email, args.index_ollama, args.elastic, args.expert, getattr(args, "upload_gdrive", False), getattr(args, "upload_gdrive_folder", None), getattr(args, "translate", False), getattr(args, "computer_vision", False))
            except Exception as e:
                print(f"Failed processing {target_url}: {e}")

                
    elif "docs.google.com/spreadsheets" in args.url:
        process_spreadsheet(args.url, args.slice, args.traverse, args.reingest, args.user_name, args.user_email, args.index_ollama, args.elastic, args.expert, getattr(args, "upload_gdrive", False), getattr(args, "upload_gdrive_folder", None), getattr(args, "translate", False))
    else:
        # Clean URL if natural language or surrounding text was provided
        clean_url = args.url.strip()
        url_match = re.search(r'https?://[^\s<>"]+', clean_url)
        if url_match:
            clean_url = url_match.group(0)
        convert_to_croissant(clean_url, args.slice, args.traverse, args.reingest, args.user_name, args.user_email, args.index_ollama, args.elastic, args.expert, getattr(args, "upload_gdrive", False), getattr(args, "upload_gdrive_folder", None), getattr(args, "translate", False), getattr(args, "computer_vision", False))
