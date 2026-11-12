# Semantic Croissant AI Studio

The platform is being tested by following European projects:
- The Climate-Adapt4EOSC project has received funding from the Horizon Europe Framework Programme under grant agreement N° 101188248.
- CDIF4EOSC: Developing and implementing the Cross-Domain Interoperability Framework for EOSC is funded by the European Union under Grant Agreement 101292473.
- AI4Social+ - AI Readiness for Social Impact aiming to integrate artificial intelligence into the social sciences and humanities (SSH) through the European Open Science Cloud (EOSC), Grant agreement ID: 101292886.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full list of components, ports, submodules and bundled code.

## Installation

1. Install Docker Engine and the Docker Compose plugin (skip this step if `docker --version` and `docker compose version` already work).

   On Linux, the official convenience script installs Docker Engine, the CLI, containerd, Buildx and Docker Compose v2:
   ```bash
   sudo apt-get update && sudo apt-get install -y curl git   # Debian/Ubuntu; use dnf/yum on RHEL/Fedora
   curl -fsSL https://get.docker.com | sudo sh
   sudo systemctl enable --now docker
   sudo usermod -aG docker $USER   # run docker without sudo (log out and back in afterwards)
   ```
   Elasticsearch also needs a higher memory-map limit:
   ```bash
   sudo sysctl -w vm.max_map_count=262144
   echo "vm.max_map_count=262144" | sudo tee /etc/sysctl.d/99-elasticsearch.conf
   ```
   Check the installation:
   ```bash
   docker --version
   docker compose version
   ```
   On macOS or Windows, install [Docker Desktop](https://docs.docker.com/desktop/) instead; it includes Docker Compose. For distribution-specific instructions, see the [Docker Engine install guide](https://docs.docker.com/engine/install/) and [Quickstart.md](Quickstart.md).

2. Clone the repository and initialize the submodules:
   ```bash
   git clone https://github.com/codata/semantic-croissant.git
   cd semantic-croissant
   git submodule update --init --recursive
   ```

3. Install Ollama with Docker and pull the default model (`gemma4:e2b`). The AI features (AI Studio chat, Ask, key-figure extraction and the MCP agent) need an Ollama endpoint for LLM inference:
   ```bash
   docker pull ollama/ollama:latest
   docker run -d --name ollama --restart unless-stopped \
     -p 11434:11434 -v ollama:/root/.ollama ollama/ollama:latest
   # On a host with an NVIDIA GPU (and nvidia-container-toolkit installed), add: --gpus=all

   docker exec ollama ollama pull gemma4:e2b
   docker exec ollama ollama list   # check that gemma4:e2b is listed
   ```
   `profiles/default.env` already points to this instance:
   ```ini
   OLLAMA_HOST=http://host.docker.internal:11434
   OLLAMA_DEFAULT_MODEL=gemma4:e2b
   ```
   To use a remote or cloud Ollama endpoint instead, change `OLLAMA_HOST` and set `OLLAMA_API_KEY` in your profile.

4. Start the infrastructure using the default local profile:
   ```bash
   docker compose --profile ./profiles/default.env up -d
   ```

5. *(Optional)* DDI-CDI Studio is not started by default. To enable it, build the image locally and add `--profile ddicdi`:
   ```bash
   git clone https://github.com/benjaminbeuster/DDICDI_generator_gen2.git tools/DDICDI_generator_gen2
   docker build -t ddicdi-studio:latest tools/DDICDI_generator_gen2
   docker compose --profile ./profiles/default.env --profile ddicdi up -d
   ```

## Documentation

- [Architecture](docs/architecture.md): components, containers, ports and submodules.
- [Configuration](docs/configuration.md): volume parameterization, isolated profiles and custom Ollama inference endpoints.
- [Data Pipeline, Ingestion and Usage Guide](docs/data-pipeline.md): JSON-LD to NTriples conversion, rebuilding the index, pre-built indexes, the ingestion API, Croissant Toolkit integration, URL ingestion and Q&A evaluation.

## Model Context Protocol (MCP) Server

The repository includes a dedicated MCP service (`mcp-croissant-live`) that exposes the Semantic Croissant index to AI assistants like Claude Desktop or Cursor. 

This enables you to ask AI assistants to "search for datasets about X" or "extract the full JSON-LD for dataset Y", and they will seamlessly execute these tasks against your live QLever instance.

### Running the MCP Service
The MCP service is automatically included when you start the `default` profile. By default, it runs as an HTTP Server-Sent Events (SSE) server exposed on port `7070`.

```bash
docker-compose --profile ./profiles/default.env up -d
```
You can connect remote MCP clients directly to `http://localhost:7070/sse`.

### Rebuilding and Restarting the MCP Service
If you make changes to the MCP server code (`api/mcp_server.py`), you can rebuild and restart the MCP container:

```bash
docker-compose --profile ./profiles/default.env up -d --build --force-recreate mcp
```

### ODRL / DID Authentication

The MCP Server integrates with the CODATA ODRL infrastructure for decentralized identity management. This ensures that any Croissant datasets or summaries you save to the Vault are properly attributed to your Decentralized Identifier (DID).

To enable ODRL Authentication:
1. Ensure the server is running (`docker compose --profile croissant-live up -d`).
2. Navigate to `https://mcp.dev.codata.org/` in your browser. This root page acts as your Authentication Dashboard.
3. Click either the **Google** or **GitHub** OAuth buttons to securely redirect to the external ODRL Wallet (`https://odrl.dev.codata.org/vcs`).
4. Once authenticated, an authorization token (`~/.odrl/authorize`) containing your DID is saved to your local machine.
5. The MCP containers automatically mount this `~/.odrl` directory. Any subsequent AI agent commands that export Croissant JSON-LD or save to the Vault will detect it and uniquely set your DID in the `creator` field.

### Document Verification and Provenance Tracking

The MCP Server implements cryptographic and structural verification of documents saved to the Vault to ensure transparent provenance tracking.

1. **Digital Signatures & DID Anchors**: When a dataset or summary is saved to the Vault via the `save_to_vault` tool, the system automatically computes the UNF-6 hash of the document and generates a Digital Signature combining your authenticated DID and the hash. This signature and a dedicated `service` verification block are embedded directly inside the `.jsonld` metadata, tying the identity of the creator cryptographically to the exact content of the file.
2. **Provenance Verification Tool**: You can verify the integrity and provenance of any document in the Vault using the `verify_document_provenance` MCP tool. By supplying the Vault filename (e.g., `kkFU1poLzxYuGowgjjIxYw.md`), the tool will read the associated `.jsonld` metadata to:
   - Validate the presence of the DID Verification Block and Digital Signature.
   - Extract and list all Creators (Human Users and AI Models) involved in the generation of the document, ensuring complete transparency of the AI/Human collaboration process.

### Connecting AI Assistants (IDEs & Desktop)

You can connect your IDEs to the public endpoint at `https://mcp.dev.codata.org/mcp` using the configurations below.

<details><summary><b>Cursor</b></summary>

Create or edit your MCP configuration file at `~/.cursor/mcp.json` or configure it directly through the Cursor Settings UI:

```json
{
  "mcpServers": {
    "croissant-mcp": {
      "type": "sse",
      "url": "https://mcp.dev.codata.org/mcp"
    }
  }
}
```
</details>

<details><summary><b>Windsurf</b></summary>

Edit your configuration file at `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "croissant-mcp": {
      "serverUrl": "https://mcp.dev.codata.org/mcp"
    }
  }
}
```
</details>

<details><summary><b>Zed</b></summary>

Because Zed natively expects `stdio` for context servers, it requires the `mcp-remote` proxy bridge to connect to remote SSE servers. Add this to your Zed `settings.json`:

```json
{
  "context_servers": {
    "croissant-mcp": {
      "command": {
        "path": "npx",
        "args": ["-y", "mcp-remote", "https://mcp.dev.codata.org/mcp"],
        "env": null
      }
    }
  }
}
```
</details>

<details><summary><b>Claude Desktop (Remote)</b></summary>

Claude Desktop also defaults to `stdio` connections. You can use the `mcp-remote` proxy bridge in your `claude_desktop_config.json` to connect to the remote server:

```json
{
  "mcpServers": {
    "croissant-mcp": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.dev.codata.org/mcp"]
    }
  }
}
```
</details>

### Local Docker Connection (Stdio)

If you are running the `semantic-croissant` stack locally via Docker, clients like Claude Desktop or Zed can bypass the network entirely and connect directly to the running container via standard input/output (`stdio`).

To do this, use the following `stdio` execution command in your client's configuration:

```json
{
  "mcpServers": {
    "croissant-local": {
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "semantic-croissant-mcp-croissant-live-1",
        "python",
        "/app/mcp_server.py"
      ]
    }
  }
}
```

Restart your IDE or Claude Desktop. You should see an icon or status indicating the tools are loaded, enabling conversational queries directly against the Croissant datasets!

## Vault Storage & UNF-6 Integrity

The Semantic Croissant ecosystem includes a dedicated object storage layer (powered by MinIO) referred to as the **Vault**. The Vault is designed to persist user interactions, AI-generated dataset summaries, and their corresponding Croissant JSON-LD metadata. 

When you use the `save_to_vault` tool through the MCP server, the content is securely saved to the Vault using a deterministic fingerprint known as the **UNF-6** (Universal Numeric Fingerprint) label.

### How the UNF-6 Label Works

To guarantee data integrity and version control, every saved file is uniquely identified by its contents. Instead of relying purely on random UUIDs, the system generates a UNF-6 hash:
1. All words within the text content are split and lexicographically sorted to neutralize minor formatting changes.
2. The sorted tokens are concatenated and hashed using SHA-256.
3. The resulting hash is truncated to 128 bits and encoded in Base64 (with URL-safe replacements).

The resulting filename adheres to the following structure:
`[prefix]_UNF-6_[hash]_[username]_[timestamp].[ext]`

For example, saving a dataset summary might produce:
`shrink_swell_risks_UNF-6_Kq4bhbZB2z4Vz5lgSYzALA_anonymous_20260810_083505.md`

This guarantees that two identical pieces of content will generate the same UNF-6 hash segment, allowing the system to easily track exact duplicates or iterations of a dataset over time. Both the unstructured Markdown (`.md`) and the structured Croissant metadata (`.jsonld`) are saved side-by-side using the same naming convention.

## FAIR Signposting Protocol

The Semantic Croissant stack implements the [FAIR Signposting Profile (Level 1)](https://signposting.org/FAIR/) to enhance the machine-actionability of all scholarly objects stored in the Vault.

When retrieving documents from the Vault, the API automatically injects HTTP `Link` headers containing persistent identifiers, metadata endpoints, and object typing. This enables automated agents and bots to intelligently traverse the scholarly web without needing to scrape HTML or parse ad-hoc formats.

### Example: Testing with cURL

You can verify the presence of the Signposting headers using a simple `GET` request. The `Link` header acts as a map for machines:

```bash
curl -v http://localhost:7070/vault/honduras_president_charges_factual_summary.md > /dev/null
```

**Expected Output:**
```http
< HTTP/1.1 200 OK
< link: <https://mcp.dev.codata.org/vault/...>; rel="cite-as", <https://mcp.dev.codata.org/vault/...jsonld>; rel="describedby" type="application/ld+json", <https://mcp.dev.codata.org/vault/...>; rel="item" type="text/markdown", <https://schema.org/Dataset>; rel="type", <https://creativecommons.org/licenses/by/4.0/>; rel="license"
< x-fair-signposting: enabled
< content-type: text/markdown; charset=utf-8
```

### Example: Testing via Model Context Protocol (MCP)

Since the MCP server acts as an intelligent proxy to the vault, AI agents inherently leverage these endpoints when reading articles using the `read_vault_article` tool. You can test this locally by querying the tool directly via the docker container:

```bash
docker exec semantic-croissant-mcp-croissant-live-1 python3 -c "
import asyncio, sys, os
sys.path.append(os.path.join(os.getcwd(), 'api'))
from mcp_server import call_tool
asyncio.run(call_tool('read_vault_article', {'url_or_filename': 'honduras_president_charges_factual_summary.md'}))
"
```

## Google Drive Integration

The MCP Server includes an optional feature to automatically upload generated Croissant (`.jsonld`) and Markdown (`.md`) files directly to a Google Drive folder. The folder is automatically named after the user's email ID.

### Setting up the Service Account

To enable this feature, you must configure a Google Service Account:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a new project (or use an existing one).
2. Enable the **Google Drive API** for your project.
3. Navigate to **IAM & Admin** > **Service Accounts** and create a new Service Account.
4. Create a new JSON key for this Service Account and download it to your local machine.
5. Save the file as `credentials.json` in the root of this project (it is mapped into the `api-croissant-live` container via the `compose.yaml` volumes).
   - Alternatively, you can specify a custom path using the `GDRIVE_CREDENTIALS_FILE` environment variable.

### Usage in MCP

When calling the `url_to_croissant` tool from your AI assistant, simply pass the `upload_gdrive: true` parameter. The server will authenticate using the mapped `credentials.json` and upload the extracted files into a Drive folder matching your ODRL/Authentication email address! If the credentials file is missing, the upload is gracefully skipped.
