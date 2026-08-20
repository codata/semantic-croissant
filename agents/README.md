# Semantic Croissant Agents

This directory contains autonomous AI agents and their configurations for interacting with the Semantic Croissant ecosystem. 

## Features

- **MCP Integration:** Agents automatically connect to the local Model Context Protocol (MCP) Server, exposing a suite of advanced data manipulation and extraction tools directly to the LLM.
- **Dynamic Tool Calling:** The agent intelligently chains together tools like `ask_expert`, `url_to_croissant`, and `extract_variables_from_croissant` based on your natural language requests.
- **Vault Persistence:** Final analytical results and extracted markdown files can be seamlessly pushed to the MinIO Vault with properly formatted Croissant JSON-LD attribution.
- **Configurable Intelligence:** Models and endpoints can be customized easily via the `agent.config` file.

## Configuration

Agent settings are managed in `agent.config`. This file controls the target LLM and MCP endpoints:

```json
{
  "OLLAMA_HOST": "http://10.147.18.82:11435",
  "MODEL": "gemma4:e4b",
  "MCP_URL": "http://localhost:7070/sse",
  "ai_model_override": "Semantic Croissant AI Agent v.0.1"
}
```

- `OLLAMA_HOST`: The endpoint for the Ollama inference server.
- `MODEL`: The specific LLM to use (e.g., `gemma4:e4b`).
- `MCP_URL`: The MCP server endpoint (defaults to SSE at port 7070).
- `ai_model_override`: The signature/attribution string appended to generated Vault datasets.

## Usage

You can trigger the agent script via the command line to perform semantic analysis tasks:

```bash
python3 agent_reference_script.py -q "Collect variables from 2 Malawi datasets?" --save-vault
```
