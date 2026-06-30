# Semantic Croissant

This repository contains the deployment infrastructure for the `croissant-live` semantic database, leveraging [QLever](https://github.com/ad-freiburg/qlever).

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
