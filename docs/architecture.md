# Architecture

The whole stack is defined in [`compose.yaml`](../compose.yaml). Settings for each deployment, such as ports and data directories, are in `profiles/<name>.env` (`profiles/default.env` for local setups).

## Components

| Component | Container | Description | Default port |
|---|---|---|---|
| **init** | `<profile>-init` | One-shot BusyBox container that sets volume ownership before the other services start | – |
| **server** | `<profile>-server` | [QLever](https://github.com/ad-freiburg/qlever) SPARQL engine holding the Croissant knowledge graph | `7011` |
| **ui** | `<profile>-ui` | QLever UI for interactive SPARQL querying | `7012` |
| **elasticsearch** | `<profile>-elasticsearch` | Elasticsearch 8.14 full-text index over datasets and Vault documents | `9200` |
| **api** | `<profile>-api` | FastAPI backend and web portal (search, Vault, collections, ingestion, rebuilds) | `7013` |
| **mcp** | `<profile>-mcp` | Model Context Protocol server (SSE / Streamable HTTP / stdio) exposing 20+ AI tools, AI Studio chat and the LLM gateway | `7070` |
| **minio** | `<profile>-minio` | S3-compatible object storage behind the Vault | `9005` (API), `9007` (console) |
| **converters** | `<profile>-converters` | CDIF / Croissant conversion service | `8082` |
| **ddicdi** *(optional, `--profile ddicdi`)* | `<profile>-ddicdi` | DDI-CDI Studio; the image has to be built locally | `8083` |

External dependency: an [Ollama](https://ollama.com) endpoint (`OLLAMA_HOST`, plus `OLLAMA_API_KEY` for cloud models) for LLM inference.

## Submodules and bundled code

- **qlever-tests**: QLever Docker build contexts, environment files, and the default `data/` and `volumes/` directories.
- **tools/converters**: Source of the CDIF converters service.
- **croissant-toolkit**: Gemini-powered skills (wizard, NLP, Croissant / RO-Crate / ODRL experts).
- **palefire** and **lot**: Supporting toolkits used by partner projects.
- **pipeline/**: Converts Croissant JSON-LD into NTriples for QLever.
- **shapes/**: SHACL shapes (`croissant.ttl`, `odrl.ttl`) used for validation.
- **agents/**: Configuration for the local AI agent (`agent.config`).
