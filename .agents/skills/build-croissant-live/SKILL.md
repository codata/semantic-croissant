---
name: build-croissant-live
description: How to build and deploy the croissant live environment inside the qlever-tests workspace using docker compose.
---
# Build Croissant Live Environment

This skill provides the steps and context necessary for building the `croissant-live` profile components within the `qlever-tests` workspace. 

## Context
The `croissant-live` profile mimics the `croissant` setup but uses different ports and volumes so it can run concurrently. Due to constraints with the current dataset (which includes multiline string literals), `QLEVER_INDEX_PARALLEL_PARSING` must be disabled during indexing.

## Process

1. **Environment Setup:**
   Create an environment file named `croissant-live.env`. It should be a copy of `croissant.env` with the following critical modifications:
   - `QLEVER_SERVER_PORT=7011`
   - `QLEVER_UI_UI_PORT=7012`
   - `QLEVER_SERVER_HOST_NAME=server-croissant-live`
   - `QLEVER_INDEX_PARALLEL_PARSING=false` (Important: Without this, the indexer will fail on multiline literals).

2. **Docker Compose Services:**
   In `compose.yaml`, the `croissant-live` profile must contain three services:
   - `server-croissant-live`: Maps port `7011:7011`, mounts `./volumes/croissant-live/server:/data`, and uses the `croissant-live.env` file.
   - `ui-croissant-live`: Maps port `7012:7012`, mounts `./volumes/croissant-live/ui:/app/db`, depends on `server-croissant-live`, and uses `croissant-live.env`.
   - `init-croissant-live`: A lightweight `busybox` container designed to run once and fix volume permissions. It runs `chown -R 65534:0` on `/data/server` and `/data/ui`.

3. **Initialization:**
   Before starting the server, run the initialization container to correct volume permissions for the Qlever user:
   ```bash
   docker compose --profile croissant-live up init-croissant-live
   ```

4. **Starting the Environment:**
   If doing this cleanly (or after deleting old index data), start the services:
   ```bash
   docker compose --profile croissant-live up -d server-croissant-live ui-croissant-live
   ```
   The `server-croissant-live` container will automatically trigger the data download (via `cp` from local data) and begin the indexing process.

5. **Monitoring Indexing:**
   The indexing takes time. You can monitor it by watching the server logs:
   ```bash
   docker compose --profile croissant-live logs -f server-croissant-live
   ```
   Once indexing completes, the server instance will automatically restart into "live" query serving mode.
