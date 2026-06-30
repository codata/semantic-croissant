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
By default, the Docker compose configuration uses volumes located at `/mediaquantum/qlever/qlever-tests/volumes` and raw data from `/mediaquantum/qlever/qlever-tests/data`.

You can override these directories by providing environment variables before running docker-compose:

```bash
VOLUME_DIR=/path/to/my/volumes DATA_DIR=/path/to/my/data docker compose --profile croissant-live up -d
```
