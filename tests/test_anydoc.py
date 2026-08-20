import anydoc
import urllib.request

url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    data = response.read()

try:
    md = anydoc.to_markdown_bytes(data)
    print(md[:100])
except Exception as e:
    print(e)
