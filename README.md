# Semantic Croissant

This repository contains the deployment infrastructure for the `croissant-live` semantic database, leveraging [QLever](https://github.com/ad-freiburg/qlever).

This development is funded by:
- The Climate-Adapt4EOSC project has received funding from the Horizon Europe Framework Programme under grant agreement N° 101188248.
- CDIF4EOSC: Developing and implementing the Cross-Domain Interoperability Framework for EOSC is funded by the European Union under Grant Agreement 101292473.

## Architecture
- **qlever-tests**: The original `qlever-tests` repository is linked here as a **Git Submodule**. This provides access to the required environment variables (`.env` files) and Docker build contexts (`Dockerfile`s).
- **compose.yaml**: The Docker Compose file defines the `croissant-live` profile to run the server and UI concurrently with standard QLever components.

## Deploying

1. Ensure the submodule is fully initialized:
   ```bash
   git submodule update --init --recursive
   ```

2. Start the infrastructure:
   ```bash
   docker compose --profile croissant-live up -d
   ```

### Volume Parameterization
By default, the Docker compose configuration uses volumes located at `./qlever-tests/volumes` and raw data from `./qlever-tests/data`.

You can override these directories by providing environment variables before running docker-compose:

```bash
VOLUME_DIR=/path/to/my/volumes DATA_DIR=/path/to/my/data docker compose --profile croissant-live up -d
```

## Data Conversion Pipeline

Before the `croissant-live` index can be built, the raw Croissant JSON-LD files must be converted into a continuous NTriples format (`.nt`) suitable for QLever ingestion.

The conversion pipeline script `convert_all.py` (located in the `pipeline/` directory) uses multiprocessing to quickly transform the source JSON-LD files. 

### Running the Conversion
If you have a directory of raw Croissant JSON-LD files (e.g., in `../croissant`), you can run the pipeline to generate a consolidated `data.nt` file ready for ingestion:

```bash
python3 pipeline/convert_all.py ../croissant ./qlever-tests/data/data.nt
```

This will produce `data/data.nt`, which is automatically mounted and read by the `server-croissant-live` container when indexing begins.

### Managing Volumes and Rebuilding the Index
If you run the pipeline again to produce a new or updated `data.nt` file, you must force QLever to rebuild the internal graph index. QLever will not automatically re-index if the old index cache files still exist in the server volume.

To update the data and restart the services:

1. Ensure your updated `data.nt` file is placed in the configured data directory (by default, `./qlever-tests/data/data.nt`).
2. Bring down the currently running services:
   ```bash
   docker compose --profile croissant-live down
   ```
3. Remove the old QLever index cache files. Because these files are created by the Docker root user, you can use a transient Alpine container to delete them cleanly from the volume folder:
   ```bash
   docker run --rm -v $(pwd)/qlever-tests/volumes/croissant-live/server:/server alpine sh -c "rm -f /server/croissant.*"
   ```
4. Restart the services:
   ```bash
   docker compose --profile croissant-live up -d
   ```

Upon startup, the server will detect that the index files are missing and automatically parse the new `data/data.nt` file to rebuild the index from scratch.

### Using Pre-built Indexes
If you already possess the pre-built QLever index files (such as `croissant.index.*`, `croissant.vocabulary.*`, etc.) from another machine or backup, you can entirely skip the lengthy index building phase.

1. Ensure the `server-croissant-live` container is stopped.
2. Copy all your pre-built index files directly into the mounted server volume directory. By default, this is:
   ```bash
   ./qlever-tests/volumes/croissant-live/server/
   ```
   *(If you customized `$VOLUME_DIR`, place them in `$VOLUME_DIR/croissant-live/server/`)*
3. Ensure the files are named correctly (e.g., prefixed with `croissant.`) and belong to the correct permissions (the QLever Docker container reads them as user `65534:0`).
4. Run `docker compose --profile croissant-live up -d`. The server will instantly detect the existing index and load the graph into memory.

## Data Ingestion (API)

The Semantic Croissant stack includes a FastAPI service that exposes endpoints for dynamically ingesting new Croissant JSON-LD data into the QLever triple store. The API runs by default on port `7013`.

### Adding a New Dataset

You can add a new Croissant JSON-LD dataset using the `/add_record` POST endpoint. By default, this will append the converted data to the persistent `data.nt` file and attempt a live `INSERT DATA` query to the running QLever instance, making the data instantly queryable without downtime.

```bash
curl -X POST "http://localhost:7013/add_record" \
     -H "Content-Type: application/json" \
     -d @my_dataset.json
```

### Triggering an Offline Rebuild

If you want to additionally trigger a full offline index rebuild (which is useful if the live insertion fails or you want to ensure total consistency), you can pass the `rebuild=true` query parameter:

```bash
curl -X POST "http://localhost:7013/add_record?rebuild=true" \
     -H "Content-Type: application/json" \
     -d @my_dataset.json
```

You can also trigger a manual index rebuild directly without adding new data using the `/rebuild` endpoint:

```bash
curl -X POST "http://localhost:7013/rebuild"
```

## Croissant Toolkit Integration

The repository includes the [Croissant Toolkit](https://github.com/codata/croissant-toolkit) as a git submodule. This Gemini-powered toolkit can automatically generate, enrich, and translate Croissant metadata from raw data or web pages.

### Automated Generation & Ingestion Workflow
You can use the toolkit to generate a dataset and instantly ingest it into QLever:

1. **Generate Metadata:** Use the toolkit's Wizard or Croissant Expert to generate a `.jsonld` file.
   ```bash
   export GEMINI_API_KEY="your-api-key"
   python3 croissant-toolkit/.gemini/skills/wizard/scripts/wizard.py "https://example.com/dataset" "My Dataset"
   ```
2. **Ingest into QLever:** Once the toolkit generates the `dataset.jsonld`, use the Semantic Croissant API to ingest it:
    ```bash
    curl -X POST "http://localhost:7013/add_record" \
         -H "Content-Type: application/json" \
         -d @croissant-toolkit/data/croissant/dataset.jsonld
    ```

## Usage Guide: URL Ingestion and Q&A

You can directly ingest content from a URL (such as a YouTube video transcript or a web article), convert it into Croissant format, and test the semantic accuracy using our built-in scripts.

### 1. Ingesting a URL
Use the `url_to_croissant.py` converter to download content, generate metadata, slice it into manageable chunks, and perform a dry-run ingestion into the Ollama model.

```bash
# Example: Ingesting a YouTube Video
OLLAMA_HOST="http://10.147.18.37:11434" python3 convertors/url_to_croissant.py "https://www.youtube.com/watch?v=OcufTCr3RQs" --slice
```
This script will produce a `_croissant.jsonld` file containing all the sliced semantic chunks, along with their text content and generated summaries.

### 2. Batch Ingesting from Google Sheets
You can also pass a Google Sheets URL containing a list of URLs to ingest them in bulk. The script will fetch the spreadsheet, extract all valid links, and process them in parallel using the `--workers` flag.

```bash
# Example: Batch ingesting URLs from a Google Sheet using 10 concurrent workers
OLLAMA_HOST="http://10.147.18.37:11434" python3 convertors/url_to_croissant.py --workers 10 "https://docs.google.com/spreadsheets/d/1g8rqbLssGL7lDOGj5nwgXlyDqxrWOQim/edit?gid=573917078#gid=573917078"
```

### 3. Asking Questions (Q&A Evaluation)
Once the dataset is converted, you can run the QA accuracy script to automatically ask questions about the text segments and evaluate the answers (with precise provenance).

```bash
# Example: Running the QA evaluator
OLLAMA_HOST="http://10.147.18.37:11434" python scripts/test_qa_accuracy.py my_dataset__croissant.jsonld
```
The script will loop through the ingested chunks, generate contextual questions, answer them, and evaluate the response's Accuracy and Precision on a 1-5 scale.

## Model Context Protocol (MCP) Server

The repository includes a dedicated MCP service (`mcp-croissant-live`) that exposes the Semantic Croissant index to AI assistants like Claude Desktop or Cursor. 

This enables you to ask AI assistants to "search for datasets about X" or "extract the full JSON-LD for dataset Y", and they will seamlessly execute these tasks against your live QLever instance.

### Running the MCP Service
The MCP service is automatically included when you start the `croissant-live` profile. By default, it runs as an HTTP Server-Sent Events (SSE) server exposed on port `7070`.

```bash
docker compose --profile croissant-live up -d
```
You can connect remote MCP clients directly to `http://localhost:7070/sse`.

### Rebuilding and Restarting the MCP Service
If you make changes to the MCP server code (`api/mcp_server.py`), you need to rebuild the API Docker image and restart the MCP container:

```bash
docker build -t api-croissant-live api/
docker compose --profile croissant-live up -d --force-recreate mcp-croissant-live
```

### ODRL / DID Authentication

The MCP Server integrates with the CODATA ODRL infrastructure for decentralized identity management. This ensures that any Croissant datasets or summaries you save to the Vault are properly attributed to your Decentralized Identifier (DID).

To enable ODRL Authentication:
1. Ensure the server is running (`docker compose --profile croissant-live up -d`).
2. Navigate to `https://mcp.dev.codata.org/` in your browser. This root page acts as your Authentication Dashboard.
3. Click either the **Google** or **GitHub** OAuth buttons to securely redirect to the external ODRL Wallet (`https://odrl.dev.codata.org/vcs`).
4. Once authenticated, an authorization token (`~/.odrl/authorize`) containing your DID is saved to your local machine.
5. The MCP containers automatically mount this `~/.odrl` directory. Any subsequent AI agent commands that export Croissant JSON-LD or save to the Vault will detect it and uniquely set your DID in the `creator` field.

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
