# Semantic Croissant — Developer Guide & Context

## Project Overview

`semantic-croissant` manages the deployment infrastructure for the **Croissant-Live** semantic database. It leverages [QLever](https://github.com/ad-freiburg/qlever) for high-performance SPARQL queries and graph storage, turning raw Croissant JSON-LD files into a continuously indexed Triple Store. On top of this, it provides:

- A **FastAPI** layer (`api/main.py`) for live data ingestion, search, and variable extraction.
- An **MCP Server** (`api/mcp_server.py`, ~4300 lines) exposing 20+ tools to AI assistants via stdio, SSE, and Streamable HTTP.
- An **AI Gateway** that proxies Anthropic-compatible API requests to local Ollama models.
- A **Vault** (MinIO) for persistent storage of AI-generated summaries and their Croissant JSON-LD metadata.
- A rich **Web UI** for browsing, reading, and interacting with Vault documents.

This development is funded by:
- The **Climate-Adapt4EOSC** project (Horizon Europe, Grant N° 101188248).
- **CDIF4EOSC**: Cross-Domain Interoperability Framework for EOSC (Grant 101292473).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Database / Graph Store | QLever (Dockerized) |
| Full-Text Search | Elasticsearch 8.x |
| Object Storage (Vault) | MinIO |
| Backend API | Python, FastAPI, RDFLib, httpx |
| MCP Server | Python MCP SDK, Starlette, Click |
| AI Inference | Ollama (local or remote), Anthropic-compatible Gateway |
| Frontend | Static HTML/CSS/JS (`api/static/`) |
| SHACL Validation | `shapes/croissant.ttl`, `shapes/odrl.ttl` |
| Deployment | Docker Compose (multi-profile) |
| Submodules | `qlever-tests`, `croissant-toolkit` |

---

## Quick Start Commands

```bash
# Initialize submodules
git submodule update --init --recursive

# Build the API image
docker build -t api-croissant-live api/

# Start the full stack
docker compose --profile croissant-live up -d

# Stop the stack
docker compose --profile croissant-live down

# Run a specific profile (e.g., ca4eosc)
PROFILE_NAME=ca4eosc docker compose --env-file profiles/ca4eosc.env -p ca4eosc --profile ca4eosc up -d
```

---

## Architecture Components

### Docker Services (`compose.yaml`)

| Service | Purpose | Default Port |
|---|---|---|
| `server` | QLever SPARQL server | 7011 |
| `ui` | QLever native UI | 7012 |
| `api` | FastAPI backend | 7013 |
| `mcp` | MCP Server (SSE + Streamable HTTP) | 7070 |
| `elasticsearch` | Full-text search engine | 9200 |
| `minio` | Object storage (Vault) | 9005 (API), 9007 (Console) |
| `init` | Volume permissions bootstrap | — |

### Key Files

- **`api/main.py`** — FastAPI application: live `add_record` insertion, index rebuild, dataset search, keyword search, SPARQL catalog, Ollama gateway proxy, variable extraction endpoints.
- **`api/mcp_server.py`** — The MCP Server: 20+ registered tools, HTTP route table, AI gateway proxy, Vault CRUD, Collections/Groups API, Expert index proxy, Streamable HTTP + SSE transports.
- **`compose.yaml`** — Multi-profile Docker orchestration.
- **`pipeline/convert_all.py`** — Batch JSON-LD → NTriples conversion.
- **`convertors/url_to_croissant.py`** — URL scraping → Croissant JSON-LD + Markdown generation.
- **`agents/agent_reference_script.py`** — Autonomous AI agent with MCP tool chaining.
- **`agents/extract_keyfigures.py`** — Key figure extraction engine.
- **`shapes/`** — SHACL shapes for Croissant and ODRL validation.

### Submodules

- **`qlever-tests`** — Core QLever env vars, Dockerfiles, volume/data directories.
- **`croissant-toolkit`** — Gemini-powered AI toolkit: Wizard, NLP Expert, Croissant Expert, RO-Crate Expert, ODRL Expert skills.

---

## MCP Server — Registered Tools (20+)

### Onboarding & Navigation
| Tool | Description |
|---|---|
| `onboarding` | Instructs the LLM which tools to select based on user intent. Must be called first. |
| `planner` | Navigation guide for correct tool sequencing. |

### Dataset Discovery
| Tool | Description |
|---|---|
| `search_croissant_datasets` | Search the QLever graph with keywords. Returns JSON-LD or Markdown. |
| `get_croissant_dataset` | Retrieve full Croissant JSON-LD for a dataset by ID or URL. |
| `elasticsearch_fulltext_search` | Full-text search over indexed Croissant datasets (Markdown + metadata). |
| `ask_expert` | Query a specific Elasticsearch expert index: `croissant`, `dataverse`, `ollama`, `huggingface`, `openml`, `hips`, `honduras`. |

### Content Generation
| Tool | Description |
|---|---|
| `url_to_croissant` | Scrape any URL (web page, YouTube, Google Sheets batch) → Croissant JSON-LD + Markdown. |
| `describe_resource` | Describe any resource (local file or URL) → Croissant JSON-LD + Markdown summary. |
| `ingest_to_qlever` | Ingest a JSON-LD payload or file into the QLever database. Optional full rebuild. |

### Vault Operations
| Tool | Description |
|---|---|
| `save_to_vault` | Store content + auto-generated Croissant JSON-LD in MinIO Vault. UNF-6 fingerprinting. |
| `read_vault_article` | Read a Vault document by filename, ID, or original URL. |
| `list_vault_documents` | Browse all Vault files, with optional prefix filter. |
| `update_vault_document` | Create a new version with explicit provenance references. |
| `verify_document_provenance` | Verify DID signatures and list all human/AI creators of a document. |

### Variable & Key Figure Extraction
| Tool | Description |
|---|---|
| `extract_variables_from_croissant` | Extract column names and descriptions from a Croissant dataset. |
| `extract_variables_from_oai` | Parse OAI_ORE exports (Dataverse) for study variables. |
| `extract_keyfigures` | Extract ALL numerical data points from text → CSV format. |
| `finalize_keyfigures` | Convert extracted CSV into Croissant JSON-LD and save to Vault. |

### Collections & Groups
| Tool | Description |
|---|---|
| `search_collections` | Query Elasticsearch for user Collections. |
| `search_groups` | Query Elasticsearch for user Groups. |
| `get_collection_documents` | List all documents within a Collection. |
| `build_collection_from_expert` | Macro: query expert → auto-create Collection → fill with results. |

### Hazard Information Profiles (HIPs)
| Tool | Description |
|---|---|
| `hazards_info_profile` | Retrieve UNDRR Hazard Information Profiles from the semantic catalog. |
| `hazards_translation` | Fetch translated hazard resources by language code and HIPs code. |

### External Integrations
| Tool | Description |
|---|---|
| `google-drive` | Search, read, or upload files to Google Drive (Service Account). |
| `search_web` | Web search (exposed only to Claude Desktop clients). |

### MCP Prompts
- **`extract_keyfigures`** — Structured prompt template for numerical fact extraction with provenance anchoring.

---

## Web UI Features (`api/static/`)

The MCP server serves a rich web frontend:

| Page | Route | Description |
|---|---|---|
| Main Dashboard | `/` | Document browser, search, model selector, ODRL auth |
| Document Viewer | `/vault/doc/{id}` | Full Markdown rendering with AI Q&A, highlight approval/rejection, print view |
| Raw/Print View | `/vault/doc/raw/{id}` | Clean printable Markdown output |
| Collection Viewer | `/collections/{id}` | Browse Collection contents |
| Group Viewer | `/groups/{id}` | Browse Group contents |

### Document Viewer Features
- **AI Q&A** (`/vault/ask`): Ask questions about document content using any available Ollama model.
- **Model Selector** (`/vault/models`): Dynamically list all models from configured Ollama endpoints.
- **Highlight Approval** (`/vault/approve/{id}`): Approve, reject, hide, or annotate text snippets → saved as new Vault artifacts with provenance links.
- **Make Public** (`/vault/public/{id}`): Toggle document visibility.
- **Document History** (`/vault/history`): Browse Elasticsearch-indexed document timeline.
- **Inline Editing** (`/vault/doc/update/{id}`): Update document content and metadata.

---

## AI Gateway (`/gateway/`)

The MCP server includes an **Anthropic-compatible API Gateway** that proxies requests to local Ollama models:

| Endpoint | Description |
|---|---|
| `/gateway/v1/chat/completions` | Proxied chat completions (OpenAI format) |
| `/v1/models` | Model listing (injects local model names into Claude model IDs) |
| `/v1/messages` | Anthropic Messages API proxy |
| `/gateway/v1/tools` | List available MCP tools for gateway clients |
| `/gateway/v1/tools/execute` | Execute MCP tools from gateway clients |

**Authentication**: API key via `X-API-Key` header or `Authorization: Bearer` token. Also accepts ODRL token authentication.

**Multi-endpoint routing**: The gateway reads `gateway_config.json` to discover multiple Ollama backends and routes requests to whichever endpoint hosts the requested model.

---

## Data Pipeline & Ingestion

1. **Offline Conversion**: `python3 pipeline/convert_all.py <input_dir> <output.nt>` — Batch JSON-LD → NTriples.
2. **Live Ingestion** (`POST /add_record`): Append to `data.nt` + live `INSERT DATA` to QLever. Zero downtime.
3. **Full Rebuild** (`POST /rebuild`): Background task to rebuild the entire QLever index.
4. **URL Ingestion** (`url_to_croissant` tool or `convertors/url_to_croissant.py`): Scrape web pages, YouTube transcripts, Google Sheets → Croissant JSON-LD.
5. **Batch Processing**: Pass a Google Sheets URL to `url_to_croissant` to ingest all URLs found in the spreadsheet.

---

## Vault Storage & UNF-6 Integrity

Files saved to the Vault are named using a **UNF-6** (Universal Numeric Fingerprint) label:
```
[prefix]_UNF-6_[hash]_[username]_[timestamp].[ext]
```
- Content words are sorted lexicographically, hashed with SHA-256, truncated to 128 bits, and Base64-encoded.
- Both `.md` (Markdown) and `.jsonld` (Croissant metadata) are saved side-by-side.
- **FAIR Signposting** headers (`Link`, `x-fair-signposting`) are injected on every Vault response.

---

## ODRL / DID Authentication

- OAuth via Google or GitHub → ODRL Wallet (`https://odrl.dev.codata.org/vcs`).
- Authorization token stored at `~/.odrl/authorize`.
- DID is embedded in Croissant `creator` and `service` verification blocks.
- Docker containers auto-mount `~/.odrl` for seamless agent identity.

---

## Profiles

Environment profiles in `profiles/` enable isolated multi-tenant deployments:

| Profile | File |
|---|---|
| `croissant-live` | `profiles/croissant-live.env` |
| `codata` | `profiles/codata.env` |
| `codata-dev` | `profiles/codata-dev.env` |
| `ca4eosc` | `profiles/ca4eosc.env` |
| `cdif4eosc` | `profiles/cdif4eosc.env` |

Each profile sandboxes QLever indexes, Elasticsearch volumes, and MinIO data.

---

## Expert Indexes (Elasticsearch)

The system maintains dedicated Elasticsearch indexes that can be queried via the `ask_expert` tool:

| Index | Content |
|---|---|
| `croissant` | Croissant datasets from the QLever store |
| `dataverse` | Datasets from Dataverse repositories |
| `ollama` | Ollama model registry metadata |
| `huggingface` | HuggingFace datasets and models |
| `openml` | OpenML experiment datasets |
| `hips` | UNDRR Hazard Information Profiles |
| `honduras` | Honduras-specific datasets and variables |

---

## Google Drive Integration

- Upload generated `.jsonld` and `.md` files to Google Drive using a Service Account.
- Credentials at `credentials.json` (root), mounted into containers.
- Files organized into per-user folders (based on ODRL email).
- Supports `suggest_mode` for draft annotations (formatted in red).

---

## Testing

- **Test Suite**: `tests/` directory contains 68 test scripts.
- **Runner**: `python3 tests/run_all_tests.py` executes all tests sequentially.
- Tests cover: MCP tools, API endpoints, Elasticsearch, MinIO, Vault operations, URL conversion, OAI parsing, Claude integration, Google Drive, agents, and more.

---

## Convertors (`convertors/`)

| Module | Description |
|---|---|
| `url_to_croissant.py` | Main URL → Croissant converter (supports web, YouTube, Google Sheets batch) |
| `oai_to_croissant.py` | OAI_ORE/Dataverse → Croissant JSON-LD |
| `openml.py` | OpenML dataset → Croissant JSON-LD |
| `gdrive_utils.py` | Google Drive upload/search/read utilities |
| `export-intelligence.py` | Intelligence export for downstream analysis |

---

## SHACL Validation (`shapes/`)

- `shapes/croissant.ttl` — MLCommons Croissant schema constraints.
- `shapes/odrl.ttl` — ODRL policy shape constraints.
- `shapes/validate.py` — Validate JSON-LD against SHACL shapes.

---

## Agents (`agents/`)

Autonomous AI agents with MCP integration:
- **`agent_reference_script.py`** — Multi-tool chaining agent driven by Ollama. Configurable via `agent.config`.
- **`extract_keyfigures.py`** — Key figure extraction engine with CSV output and provenance anchoring.
- **`agent.config`** — Configures `OLLAMA_HOST`, `MODEL`, `MCP_URL`, and attribution string.

---

## MCP Transport Protocols

| Protocol | Endpoint | Use Case |
|---|---|---|
| SSE | `/sse`, `/mcp/sse` | IDE connections (Cursor, Windsurf) |
| Streamable HTTP | `/mcp`, `/mcp/` | Modern MCP clients |
| stdio | `docker exec -i <container> python /app/mcp_server.py` | Claude Desktop, Zed |

---

## IDE Integration

Supported IDEs: **Cursor**, **Windsurf**, **Zed**, **Claude Desktop**, **VS Code**, **Codex**.
Configuration guides available in `integrations/` and `README.md`.

Public endpoint: `https://mcp.dev.codata.org/mcp`
