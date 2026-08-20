import markdown
from xml.etree import ElementTree as ET

md = """
# Test
This is a **bold** and *italic* paragraph with a [link](https://google.com).
- List item 1
- List item 2
"""

html = markdown.markdown(md)
print(html)
