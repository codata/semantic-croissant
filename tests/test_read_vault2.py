def get_filename(url_or_filename):
    filename = url_or_filename
    if filename.startswith("http://") or filename.startswith("https://"):
        import urllib.parse
        parsed_url = urllib.parse.urlparse(filename)
        path = parsed_url.path.rstrip("/")
        if "/vault/" in path:
            filename = path.split("/vault/")[-1]
        else:
            safe_name = parsed_url.netloc + path
            safe_name = safe_name.replace("/", "_").replace(".", "_")
            if parsed_url.query:
                qs = urllib.parse.parse_qsl(parsed_url.query)
                for k, v in qs:
                    safe_name += "_" + v
            if not safe_name:
                safe_name = "url_output"
            filename = f"{safe_name}_content.md"
            
    if not filename.endswith(".md") and not filename.endswith(".jsonld") and not filename.endswith(".gz") and not filename.endswith(".csv"):
        filename += ".md"
    return filename

print(get_filename("QkGa7EsMlhLkWqF4phxLVQ"))
print(get_filename("QkGa7EsMlhLkWqF4phxLVQ.md"))
print(get_filename("https://ai.mediaquantum.eu/vault/QkGa7EsMlhLkWqF4phxLVQ"))
print(get_filename("https://ai.mediaquantum.eu/vault/QkGa7EsMlhLkWqF4phxLVQ.md"))
