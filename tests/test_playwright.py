import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'convertors'))
from url_to_croissant import fetch_with_playwright

url = "https://dataverse.harvard.edu/api/info/version"
try:
    content = fetch_with_playwright(url)
    print("Content Length:", len(content))
    print(content[:500])
except Exception as e:
    print(e)
