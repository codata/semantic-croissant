import sys
import os
import requests
import json
import argparse
import hashlib
import base64
import io
import csv

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://10.147.18.82:11435")
MODEL = "gemma4:e4b"

def compute_unf6(content):
    words = sorted(content.split())
    c = b""
    for w in words:
        c += w.encode("utf-8") + b"\n\x00"
    d = hashlib.sha256(c).digest()[:16]
    raw_hash = base64.b64encode(d).decode("ascii")
    safe_hash = raw_hash.replace("=", "").replace("+", "").replace("/", "")
    return f"UNF-6:{safe_hash}"

def extract_keyfigures(content, blocksize=4096):
    doc_hash = compute_unf6(content)
    
    # Split markdown in paragraphs and group into blocks
    raw_paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    blocks = []
    current_block = ""
    current_paragraphs = []
    
    for idx, p in enumerate(raw_paragraphs, start=1):
        if len(p) < 10:
            continue
        if len(current_block) + len(p) > blocksize and current_block:
            blocks.append((current_paragraphs, current_block))
            current_block = p
            current_paragraphs = [idx]
        else:
            current_block += "\n\n" + p if current_block else p
            current_paragraphs.append(idx)
            
    if current_block:
        blocks.append((current_paragraphs, current_block))
    
    final_output_io = io.StringIO()
    final_writer = csv.writer(final_output_io)
    final_writer.writerow(['Conceptual Variable', 'Represented Variable', 'Instance Variable', 'Unit of Measure', 'Value', 'Provenance Anchor'])
    
    seen_rows = set()
    
    print(f"Document hash: {doc_hash}")
    print(f"Total blocks to process: {len(blocks)} (grouped from {len(raw_paragraphs)} paragraphs)")

    import re
    def split_into_sentences(text):
        # Basic heuristic sentence splitter
        sentences = re.split(r'(?<=[.!?]) +(?=[A-Z0-9])', text.replace('\n', ' '))
        return [s.strip() for s in sentences if s.strip()]
        
    def traceback_sentence_id(row, sentences):
        if len(row) < 5:
            return "s?"
        value = str(row[4]).lower()
        iv = str(row[2]).lower()
        
        best_match_idx = -1
        best_score = -1
        
        for idx, s in enumerate(sentences, start=1):
            s_lower = s.lower()
            score = 0
            if value != 'n/a' and value in s_lower:
                score += 2
            if iv != 'n/a' and iv in s_lower:
                score += 1
                
            if score > best_score and score > 0:
                best_score = score
                best_match_idx = idx
                
        if best_match_idx != -1:
            return f"s{best_match_idx}"
        
        # Fallback to simple subset match on any field if value/iv failed
        for idx, s in enumerate(sentences, start=1):
            s_lower = s.lower()
            if value != 'n/a' and value in s_lower:
                return f"s{idx}"
                
        return "s?"

    def process_block(args):
        block_idx, block_info, doc_hash, total = args
        paragraph_indices, block_text = block_info
        
        if len(paragraph_indices) == 1:
            base_anchor = f"{doc_hash}#p{paragraph_indices[0]}"
        else:
            base_anchor = f"{doc_hash}#p{paragraph_indices[0]}-p{paragraph_indices[-1]}"
            
        sentences = split_into_sentences(block_text)
        
        prompt = (
            "Extract all important numbers, key figures, and numerical data points from the following text.\n"
            "Do NOT group multiple entities into a single row. For example, if the text says 'Google: $4.2T, Meta: $1.4T', you must create completely separate rows for Google and Meta.\n\n"
            f"Text to analyze:\n{block_text}\n\n"
            "Respond ONLY with a CSV block formatted exactly as below. If there are no key figures in the text, respond with 'NO_DATA'.\n"
            "```csv\n"
            "Conceptual Variable,Represented Variable,Instance Variable,Unit of Measure,Value\n"
        )

        payload = {
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0
            }
        }

        print(f"Processing block {block_idx}/{total}...")
        extracted_rows = []
        try:
            response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=300)
            response.raise_for_status()
            data = response.json()
            result = data.get("response", "").strip()
            
            if "NO_DATA" in result or not result:
                return []
                
            # Parse output
            lines = result.strip().split('\n')
            is_markdown = any(line.strip().startswith('|') for line in lines)
            
            output_io = io.StringIO()
            writer = csv.writer(output_io)
            
            if is_markdown:
                for line in lines:
                    line = line.strip()
                    if line.startswith('|') and not line.startswith('| :---') and 'Conceptual Variable' not in line:
                        row = [cell.strip() for cell in line.strip('|').split('|')]
                        if len(row) >= 5:
                            writer.writerow(row[:5])
            else:
                csv_content = ""
                if "```csv" in result:
                    parts = result.split("```csv")
                    if len(parts) > 1:
                        csv_content = parts[1].split("```")[0].strip()
                elif "```" in result:
                    parts = result.split("```")
                    if len(parts) > 1:
                        csv_content = parts[1].strip()
                else:
                    csv_lines = [line for line in lines if "," in line]
                    if len(csv_lines) > 2:
                        csv_content = "\n".join(csv_lines)
                        
                if csv_content:
                    input_io = io.StringIO(csv_content)
                    reader = csv.reader(input_io)
                    for row in reader:
                        if len(row) >= 5 and "Conceptual Variable" not in row[0]:
                            writer.writerow(row[:5])
            
            extracted_csv = output_io.getvalue().strip()
            if extracted_csv:
                reader = csv.reader(io.StringIO(extracted_csv))
                for row in reader:
                    if len(row) >= 5:
                        # Traceback to sentence ID
                        sid = traceback_sentence_id(row, sentences)
                        anchor = f"{base_anchor}_{sid}"
                        
                        # Append the provenance anchor
                        full_row = row[:5] + [anchor]
                        extracted_rows.append(full_row)
        except Exception as e:
            print(f"Error processing block {block_idx}: {e}")
        
        return extracted_rows

    import concurrent.futures
    tasks = [(idx, b, doc_hash, len(blocks)) for idx, b in enumerate(blocks, start=1)]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(process_block, tasks)
        
        for rows in results:
            for full_row in rows:
                row_tuple = tuple(full_row)
                if row_tuple not in seen_rows:
                    seen_rows.add(row_tuple)
                    final_writer.writerow(full_row)

    print("\n--- EXTRACTED KEY FIGURES (CSV) ---\n")
    csv_result = final_output_io.getvalue()
    print(csv_result)
    print("--------------------------------------------\n")
    return csv_result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract key figures from a markdown file.")
    parser.add_argument("file_path", help="Path to the markdown file to process or vault filename.")
    parser.add_argument("--format", choices=["csv", "json-ld"], default="csv", help="Output format (csv or json-ld)")
    parser.add_argument("--blocksize", type=int, default=4096, help="Maximum characters per block (default 4096)")
    args = parser.parse_args()
    
    content = ""
    file_path = args.file_path.strip()
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        url = f"https://mcp.dev.codata.org/vault/{file_path}"
        if file_path.startswith("http"):
            url = file_path
            
        print(f"File not found locally. Attempting to fetch from vault or URL: {url}")
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            content = resp.text
            print("Successfully downloaded file.")
            if "text/html" in resp.headers.get("Content-Type", "") or content.strip().lower().startswith("<html"):
                try:
                    import markdownify
                    content = markdownify.markdownify(content, heading_style="ATX").strip()
                    print("Converted HTML to markdown.")
                except ImportError:
                    pass
        except Exception as e:
            print(f"Error: File not found locally and failed to download from vault: {e}")
            sys.exit(1)
            
    csv_output = extract_keyfigures(content, blocksize=args.blocksize)
    
    if args.format == "json-ld" and csv_output:
        reader = csv.reader(io.StringIO(csv_output))
        header = next(reader, None)
        variables = []
        row_idx = 1
        
        for row in reader:
            if len(row) < 6: continue
            cv, rv, iv, unit, val, anchor = row[:6]
            var_id = f"ex:extracted/iv/var_{row_idx}"
            
            var_obj = {
                "@id": var_id,
                "@type": ["cdi:InstanceVariable", "schema:PropertyValue"],
                "schema:name": cv,
                "schema:description": rv,
                "schema:alternateName": [iv],
                "schema:unitText": unit,
                "schema:value": val,
                "schema:subjectOf": anchor
            }
            variables.append(var_obj)
            row_idx += 1
            
        # Group variables by their exact sentence anchor
        anchor_map = {}
        for var in variables:
            anchor = var.get("schema:subjectOf")
            if anchor not in anchor_map:
                anchor_map[anchor] = []
            anchor_map[anchor].append(var["@id"])
            
        # Add isRelatedTo edges for variables originating from the same sentence
        for var in variables:
            anchor = var.get("schema:subjectOf")
            related_ids = [v for v in anchor_map.get(anchor, []) if v != var["@id"]]
            if related_ids:
                var["schema:isRelatedTo"] = [{"@id": rid} for rid in related_ids]
                
        base_url = f"https://mcp.dev.codata.org/vault/{file_path}" if not file_path.startswith("http") else file_path
        
        jsonld_doc = {
            "@context": {
                "schema": "http://schema.org/",
                "cdi": "http://ddialliance.org/Specification/DDI-CDI/1.0/RDF/",
                "cdif": "https://cdif.org/1.1/",
                "ex": base_url
            },
            "@id": "ex:dataset/extracted_keyfigures",
            "@type": ["schema:Dataset"],
            "schema:name": "Extracted Key Figures",
            "schema:variableMeasured": variables
        }
        
        print("\n--- EXTRACTED KEY FIGURES (JSON-LD) ---\n")
        print(json.dumps(jsonld_doc, indent=2))
        print("--------------------------------------------\n")
