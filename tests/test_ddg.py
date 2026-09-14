import requests
from bs4 import BeautifulSoup

def search_ddg(query):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res = requests.get(f"https://html.duckduckgo.com/html/?q={query}", headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")
    results = []
    for a in soup.find_all("a", class_="result__url"):
        url = a.get("href")
        title_tag = a.find_previous("a", class_="result__snippet")
        if title_tag:
            results.append({"url": url, "snippet": title_tag.text})
    return results

print(search_ddg("semantic croissant"))
