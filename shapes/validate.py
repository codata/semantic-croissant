import sys
import argparse
import urllib.request
from pyshacl import validate

def validate_jsonld(data_file, shapes_file):
    try:
        # If the data_file is a URL, fetch it first
        if data_file.startswith("http://") or data_file.startswith("https://"):
            req = urllib.request.Request(data_file, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp:
                data_payload = resp.read().decode('utf-8')
        else:
            data_payload = data_file
            
        conforms, v_graph, v_text = validate(
            data_payload,
            shacl_graph=shapes_file,
            data_graph_format='json-ld',
            shacl_graph_format='turtle',
            inference='rdfs',
            debug=False,
            serialize_report_graph=True
        )
        return conforms, v_text
    except Exception as e:
        print(f"Error during validation: {e}")
        return False, str(e)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate JSON-LD files against SHACL shapes.")
    parser.add_argument("data_file", help="Path or URL to the JSON-LD data file")
    parser.add_argument("--shapes", nargs='+', default=["shapes/croissant.ttl", "shapes/odrl.ttl"], help="Path(s) to the SHACL shapes file(s) (default: shapes/croissant.ttl shapes/odrl.ttl)")
    
    args = parser.parse_args()
    
    overall_conforms = True
    for shape_file in args.shapes:
        print(f"Validating {args.data_file} against {shape_file}...")
        conforms, report_text = validate_jsonld(args.data_file, shape_file)
        
        print(f"\\nConforms ({shape_file}): {conforms}\\n")
        if not conforms:
            print(f"Validation Report for {shape_file}:")
            print(report_text)
            overall_conforms = False
            
    if not overall_conforms:
        sys.exit(1)
    else:
        print("All validations successful!")
        sys.exit(0)
