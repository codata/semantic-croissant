import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'crawler'))
import converters
import urllib.request

def test_conversion(url, filename):
    print(f"Testing {filename}...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        content = response.read()
    
    md = converters.convert_to_markdown(content, filename)
    if md:
        print("Success! Output snippet:")
        print(md[:300].decode('utf-8'))
        print("-" * 40)
    else:
        print("Failed or None returned.")

# Test PDF
test_conversion("https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf", "dummy.pdf")

# Test CSV
test_conversion("https://people.sc.fsu.edu/~jburkardt/data/csv/hw_200.csv", "sample.csv")
