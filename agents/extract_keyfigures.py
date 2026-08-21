import sys
import os
import requests
import json
import argparse

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://10.147.18.82:11435")
MODEL = "gemma4:e4b"

def extract_keyfigures(content):
    prompt = (
        "Extract all important numbers, key figures, and numerical data points from the following text.\n"
        "Do NOT group multiple entities into a single row. For example, if the text says 'Google: $4.2T, Meta: $1.4T', you must create completely separate rows for Google and Meta.\n\n"
        f"Text to analyze:\n{content}\n\n"
        "```csv\n"
        "Conceptual Variable,Represented Variable,Instance Variable,Unit of Measure,Value\n"
    )

    # Send request to Ollama
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0
        }
    }

    print(f"Sending request to Ollama at {OLLAMA_HOST} using model {MODEL}...")
    try:
        response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        result = data.get("response", "").strip()
        
        import io
        import csv
        
        output_io = io.StringIO()
        writer = csv.writer(output_io)
        
        # Check if it's a markdown table first
        lines = result.strip().split('\n')
        is_markdown = any(line.strip().startswith('|') for line in lines)
        
        if is_markdown:
            for line in lines:
                line = line.strip()
                if line.startswith('|') and not line.startswith('| :---') and 'Conceptual Variable' not in line:
                    # Parse markdown row
                    row = [cell.strip() for cell in line.strip('|').split('|')]
                    if len(row) >= 5:
                        writer.writerow(row[:5])
        else:
            # Try to extract CSV block
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
                    if len(row) >= 5:
                        writer.writerow(row[:5])
        
        extracted_csv = output_io.getvalue().strip()
        if extracted_csv:
            # We want the header always present in the final output
            final_output_io = io.StringIO()
            final_writer = csv.writer(final_output_io)
            final_writer.writerow(['Conceptual Variable', 'Represented Variable', 'Instance Variable', 'Unit of Measure', 'Value'])
            
            # Read the extracted rows back and write them, deduplicating exactly
            input_io = io.StringIO(extracted_csv)
            reader = csv.reader(input_io)
            seen_rows = set()
            for row in reader:
                # Convert row to a tuple so it can be hashed for the set
                row_tuple = tuple(row)
                if row_tuple not in seen_rows:
                    seen_rows.add(row_tuple)
                    final_writer.writerow(row)
                
            print("\n--- EXTRACTED KEY FIGURES (CSV) ---\n")
            csv_result = final_output_io.getvalue()
            print(csv_result)
            print("--------------------------------------------\n")
            return csv_result
        else:
            print("Error: The model failed to return a valid extraction block. Raw output:")
            print(result)
            return None

    except Exception as e:
        import traceback
        print(f"Error parsing output: {e}")
        traceback.print_exc()
        if 'result' in locals():
            print("Raw Model Output was:")
            print(result)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract key figures from a markdown file.")
    parser.add_argument("file_path", help="Path to the markdown file to process or vault filename.")
    parser.add_argument("--format", choices=["csv", "json-ld"], default="csv", help="Output format (csv or json-ld)")
    args = parser.parse_args()
    
    content = ""
    file_path = args.file_path.strip()
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        # If not found locally, check if it's a vault filename
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
            
    csv_output = extract_keyfigures(content)
    
    if args.format == "json-ld" and csv_output:
        import csv
        import io
        import json
        
        reader = csv.reader(io.StringIO(csv_output))
        header = next(reader, None)
        variables = []
        row_idx = 1
        
        for row in reader:
            if len(row) < 5: continue
            cv, rv, iv, unit, val = row[:5]
            variables.append({
                "@id": f"ex:extracted/iv/var_{row_idx}",
                "@type": ["cdi:InstanceVariable", "schema:PropertyValue"],
                "schema:name": cv,
                "schema:description": rv,
                "schema:alternateName": [iv],
                "schema:unitText": unit,
                "schema:value": val
            })
            row_idx += 1
            
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
