# Semantic Croissant - Skills & Tools Documentation

This document outlines the available capabilities (Skills and Tools) that agents, LLMs, and users can utilize when interacting with the Semantic Croissant stack.

## 1. MCP (Model Context Protocol) Tools
The MCP Server (`api/mcp_server.py`) exposes several tools to connected IDEs (Cursor, Windsurf, Zed) and Claude Desktop.

### Dataset Discovery
- **`search_croissant_datasets`**: Search for datasets using natural language queries (e.g., "climate change", "hazard profiles"). It queries the underlying QLever graph using text filters and returns results in JSON-LD or Markdown.
- **`get_croissant_dataset`**: Retrieve the full, detailed Croissant JSON-LD metadata for a specific dataset using its internal ID (e.g., `bn36`).

### Hazard Information Profiles (HIPs)
- **`hazards/info-profile`**: Retrieve metadata and `hipsCode`s for specific hazards from the local UNDRR HIPs semantic catalog.
- **`hazards/translation`**: Fetch translated hazard markdown resources based on a 2-letter language code and a specific `hipsCode`.

### Variable Extraction
- **`extract_variables_from_croissant`**: Extract column names and descriptions from a given Croissant dataset by its ID or external URL.
- **`extract_variables_from_oai`**: Parse OAI_ORE exports (like Dataverse outputs) to extract relevant study variables and questions.

### Planner
- **`planner`**: A navigation guide that instructs LLMs on the correct sequence of tools to use based on the user's intent.

## 2. Agent Skills
The repository contains custom agent skills (located in `.agents/skills/`) to help AI agents manage the infrastructure:
- **`build-croissant-live`**: Instructions for building and deploying the live environment inside the `qlever-tests` workspace via Docker compose.
- **`manage-semantic-croissant`**: Workflows for managing, deploying, and executing the offline data conversion pipeline (JSON-LD to `.nt`).

## 3. Data Ingestion API Skills
Agents can ingest and manage data dynamically using the FastAPI service (running by default on Port 7013):
- **Live Ingestion (`POST /add_record`)**: Add a new JSON-LD dataset. The API automatically converts it, appends it to `data.nt`, and injects it into the live QLever store without downtime.
- **Index Rebuild (`POST /rebuild`)**: Trigger a background task to rebuild the full QLever index from the persistent `data.nt` file and restart the server container.

## 4. Croissant Toolkit Submodule Skills
The repository embeds the [Croissant Toolkit](https://github.com/codata/croissant-toolkit), a powerful Gemini 3-powered orchestration engine. AI Agents and users can utilize the scripts in `croissant-toolkit/.gemini/skills/` to generate rich metadata before ingesting it.
- **`wizard`**: Automatically navigates, transcribes, translates, and structures raw web content or data into perfect Croissant JSON-LD.
- **`nlp-expert`**: Extracts named entities (people, places, organizations) and injects them semantically into the dataset metadata.
- **`croissant-expert`**: Enforces strict MLCommons Croissant schema constraints during generation.
