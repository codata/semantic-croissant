import html2text

html_path = "/home/tikhonov/.gemini/antigravity-ide/brain/c71eb42d-e536-4933-a2bb-21f8c1aa33ca/.system_generated/steps/210/content.md"

with open(html_path, 'r', encoding='utf-8') as f:
    html_content = f.read()

# The content has a header added by the tool: "Title: Live Content..." 
# We should parse everything after "<!DOCTYPE html>"
start_idx = html_content.find("<!DOCTYPE html>")
if start_idx != -1:
    html_content = html_content[start_idx:]

h = html2text.HTML2Text()
h.ignore_links = False
markdown_content = h.handle(html_content)

modelfile_content = f"""FROM gemma4:e2b

PARAMETER temperature 0.1
PARAMETER num_ctx 32768

SYSTEM \"\"\"You are an expert policy engineer and metadata specialist for the Open Digital Rights Language (ODRL).
Your task is to analyze, construct, and validate data policies according to the ODRL Formal Semantics specification.

Here is the ODRL Formal Semantics Specification:
---
{markdown_content}
---

When presented with policy requirements, constraints, or a description of digital rights, always output the policy mapped to the ODRL standard in JSON-LD (or analyze the provided policy), strictly conforming to the semantics and specification provided above. Ensure that you wrap your response in valid JSON or JSON-LD blocks and accurately represent permissions, prohibitions, duties, and constraints.\"\"\"
"""

with open("/mediaquantum/qlever/semantic-croissant/prompts/gemma-odrl.md", "w", encoding="utf-8") as f:
    f.write(modelfile_content)

print("Created ODRL Modelfile with Markdown successfully.")
