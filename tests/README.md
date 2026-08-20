# Semantic Croissant Test Suite

This directory contains the test scripts for the Semantic Croissant project. These scripts were moved here from the root directory to maintain a clean project structure. They cover a wide range of functionalities including MCP (Model Context Protocol) client/server interactions, MinIO vault operations, Elasticsearch integrations, Google Drive uploads, and LLM processing.

## Running Tests
You can run any of these Python test scripts individually. Some scripts run asynchronously and use `asyncio.run()`, while others might require specific Docker containers (like `minio` or `semantic-croissant-mcp-croissant-live-1`) to be running.

Example:
```bash
python tests/test_read_vault.py
```

## Test Overview by Category

### MCP (Model Context Protocol) Client & Server Tests
*   **`test_mcp_client.py`**, **`test_mcp.py`**, **`test_mcp_ctx.py`**, **`test_local_mcp.py`**: General tests for MCP client initialization, connection, and session management.
*   **`test_sse_client.py`**: Tests connecting to the MCP server using Server-Sent Events (SSE) over `http://localhost:7070/sse`.
*   **`test_tool.py`**: Tests calling MCP tools (e.g., `extract_variables_from_croissant`) by executing the Python MCP server inside a Docker container via `stdio`.

### Vault & Storage (MinIO) Tests
*   **`test_minio.py`**: Tests basic connectivity and operations with the MinIO storage backend.
*   **`test_save_vault.py`**: Tests the `save_to_vault` MCP tool, ensuring JSON-LD and Markdown payloads are correctly saved.
*   **`test_read_vault.py`**, **`test_read.py`**: Tests reading specific files and articles back out of the MinIO vault using MCP tools and direct HTTP requests.
*   **`test_mcp_vault.py`**: Integrates MCP client calls with Vault operations.

### External APIs & Third-Party Integrations
*   **`test_gdrive_mcp.py`**, **`test_upload.py`**, **`test_urls.py`**: Tests uploading files, resolving URLs, and managing documents within Google Drive using the MCP `handle_google_drive` tool.
*   **`test_docs_api.py`**, **`test_suggestion.py`**: Tests interactions with the Google Docs API, specifically generating blank documents and verifying 'suggest mode' edits.
*   **`test_es.py`**, **`test_es_upload.py`**: Tests connections to Elasticsearch and the uploading/indexing of generated Croissant documents.
*   **`test_playwright.py`**: Tests using Playwright for headless browser fetching and content scraping.

### Data Extraction & Conversion Tests
*   **`test_parse.py`**: Tests extracting Croissant variables from Dataverse export data.
*   **`test_oai.py`**, **`test_oai_to_croissant.py`**: Tests fetching OAI-PMH metadata and converting it to the Semantic Croissant JSON-LD format.
*   **`test_markdown_parser.py`**: Tests utilities for parsing and extracting structured elements from Markdown files.
*   **`test_converter.py`**: General conversion utility tests.
*   **`test_schema.py`**: Validates JSON-LD schema payloads.

### LLM & Agent Tests
*   **`test_ollama_performance.py`**: Benchmarks different Ollama models (`gemma`, etc.) on text generation tasks and records execution times.
*   **`test_ask_expert.py`**: Tests querying the `ask_expert` tool for semantic search and dataset retrieval.
*   **`test_honduras_agent.py`**: Specific integration test for the Honduras data collection agent workflow.
*   **`test_creator.py`**: Tests dataset creator metadata generation.

### Miscellaneous & Legacy Scripts
*   **`test_api.py`**, **`test_main.py`**, **`test_main2.py`**: Tests for primary API endpoints and core application flows.
*   **`test_fetch.py`**, **`test_fetch_old.py`**, **`test_fetch_lm.py`**, **`test_fetch_lm_2.py`**: Various iterations of HTTP fetching scripts.
*   **`test_httpx.py`**: Basic HTTPX async request testing.
*   **`test_anydoc.py`**, **`test_codex_save.py`**, **`test_complex.py`**, **`test_fallback.py`**, **`test_get_dataset.py`**, **`test_hf_dataset.py`**, **`test_mcp_ingest.py`**, **`test_mcp_url.py`**: Other specialized workflow tests covering HuggingFace dataset ingestion, complex scenarios, and fallbacks.
