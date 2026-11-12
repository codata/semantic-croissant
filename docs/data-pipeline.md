# Data Pipeline, Ingestion and Usage Guide

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
   docker-compose --profile ./profiles/default.env down
   ```
3. Remove the old QLever index cache files. Because these files are created by the Docker root user, you can use a transient Alpine container to delete them cleanly from the volume folder:
   ```bash
   docker run --rm -v $(pwd)/qlever-tests/volumes/default/server:/server alpine sh -c "rm -f /server/croissant.*"
   ```
4. Restart the services:
   ```bash
   docker-compose --profile ./profiles/default.env up -d
   ```

Upon startup, the server will detect that the index files are missing and automatically parse the new `data/data.nt` file to rebuild the index from scratch.

### Using Pre-built Indexes
If you already possess the pre-built QLever index files (such as `croissant.index.*`, `croissant.vocabulary.*`, etc.) from another machine or backup, you can entirely skip the lengthy index building phase.

1. Ensure the `default-server` container is stopped.
2. Copy all your pre-built index files directly into the mounted server volume directory. By default, this is:
   ```bash
   ./qlever-tests/volumes/default/server/
   ```
   *(If you customized `$VOLUME_DIR`, place them in `$VOLUME_DIR/default/server/`)*
3. Ensure the files are named correctly (e.g., prefixed with `croissant.`) and belong to the correct permissions (the QLever Docker container reads them as user `65534:0`).
4. Run `docker-compose --profile ./profiles/default.env up -d`. The server will instantly detect the existing index and load the graph into memory.

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
