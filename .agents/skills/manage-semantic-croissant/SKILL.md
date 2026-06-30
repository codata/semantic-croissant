---
name: manage-semantic-croissant
description: How to manage, deploy, and execute the data conversion pipeline for the semantic-croissant live infrastructure.
---

# Semantic Croissant Infrastructure Skills

This skill document defines the standard operating procedures for managing the `semantic-croissant` infrastructure.

## 1. Repository Structure
The repository is the root deployment for the live Croissant semantic graph.
- **Git Submodule (`qlever-tests`)**: Contains the Dockerfiles and environment variables. If you clone this repository, you must run `git submodule update --init --recursive`.
- **`compose.yaml`**: The primary Docker Compose file. It uses parameterized volume mounts.
- **`pipeline/`**: Contains Python scripts for data preparation.

## 2. Running the Data Conversion Pipeline
Before building a fresh index, raw JSON-LD files must be converted into NTriples (`.nt`).
1. Navigate to the root of `semantic-croissant`.
2. Execute the multiprocessing conversion script:
   ```bash
   python3 pipeline/convert_all.py /mediaquantum/qlever/croissant ./qlever-tests/data/data.nt
   ```
   *(Ensure you replace the source directory if the JSON-LD files are located elsewhere).*

## 3. Deploying the QLever Stack
The deployment consists of a backend SPARQL server and a UI frontend.

1. **Start the stack**:
   ```bash
   docker compose --profile croissant-live up -d
   ```
2. **Custom Volumes**: 
   By default, the `compose.yaml` uses relative paths (`./qlever-tests/volumes`). You can override them:
   ```bash
   VOLUME_DIR=/custom/volumes DATA_DIR=/custom/data docker compose --profile croissant-live up -d
   ```
3. **Ports**:
   - QLever Server: `7011`
   - QLever UI: `7012`

## 4. Rebuilding the Index
If the underlying `data.nt` file changes, you must rebuild the index cleanly:
1. Stop the current server: `docker compose --profile croissant-live stop server-croissant-live`
2. Remove the old index cache files from the mounted volume (requires root/docker privileges, often done via an Alpine container):
   ```bash
   docker run --rm -v $(pwd)/qlever-tests/volumes/croissant-live/server:/server alpine sh -c "rm -f /server/croissant.*"
   ```
3. Restart the server: `docker compose --profile croissant-live start server-croissant-live`
4. The server will automatically detect the missing index and begin rebuilding from `data.nt`. You can monitor this with:
   ```bash
   docker compose --profile croissant-live logs -f server-croissant-live
   ```
