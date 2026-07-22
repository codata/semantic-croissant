# Semantic Croissant - Developer Guide & Context

## Project Overview
`semantic-croissant` manages the deployment infrastructure for the `croissant-live` semantic database. It leverages [QLever](https://github.com/ad-freiburg/qlever) for high-performance SPARQL queries and graph storage, turning raw Croissant JSON-LD files into a continuously indexed Triple Store. It also features a FastAPI layer for live data ingestion and an MCP (Model Context Protocol) server to interface with AI tools.

## Tech Stack
- **Database/Graph Store:** QLever (Dockerized)
- **Backend/API:** Python, FastAPI, RDFLib
- **MCP Server:** Python MCP SDK, Starlette (SSE transport)
- **Deployment:** Docker Compose

## Quick Start Commands
- **Initialize submodule:** `git submodule update --init --recursive`
- **Start the stack:** `docker compose --profile croissant-live up -d`
- **Stop the stack:** `docker compose --profile croissant-live down`

## Key Architecture Components
- **`qlever-tests` Submodule:** Contains core environment variables and Docker configurations.
- **`api/main.py`:** The FastAPI application handling the live `add_record` insertion, index rebuilding, and HTTP dataset searches.
- **`api/mcp_server.py`:** The Model Context Protocol server exposing datasets and hazard profiles directly to IDEs (via `stdio` or `SSE`).
- **`compose.yaml`:** Orchestrates the server (`server-croissant-live`), UI (`ui-croissant-live`), API (`api-croissant-live`), and MCP proxy (`mcp-croissant-live`).

## Data Pipeline & Ingestion
Data is ingested by converting JSON-LD to `data.nt` (NTriples). Live ingestion occurs through the API (`POST /add_record`), which appends to `data.nt` and executes an `INSERT DATA` query to the live QLever index, preventing the need for downtime. A full background rebuild can be triggered via `POST /rebuild`.
