# Quickstart: Deploying Semantic Croissant on a New Server

This guide provides step-by-step instructions for installing and running **Semantic Croissant** (`croissant-live`) on a clean Linux server (Ubuntu/Debian recommended).

---

## 1. Prerequisites & System Requirements

### Hardware Recommendations
- **CPU**: 4+ cores (8+ cores recommended for indexing and ML tasks)
- **RAM**: Minimum 16 GB (Elasticsearch alone allocates 2–4 GB; QLever and local LLMs require additional memory)
- **Storage**: Minimum 50 GB free disk space (fast SSD or NVMe recommended; ramdisk can be used for high-throughput testing)

### Software Requirements
- **OS**: Linux (Ubuntu 22.04/24.04 LTS or Debian 12 recommended)
- **Git** with submodule support
- **Docker Engine** (v24.0+ or newer)
- **Docker Compose** (v2.20+ or Docker Compose plugin)
- **Node.js** (v20+ / v22+) & **npm** *(optional, only if modifying frontends locally)*
- **Python 3.12+** & **uv** / **pip** *(optional, for running offline pipeline scripts outside Docker)*



## 2. Server Environment Preparation

### Install Docker and Docker Compose plugin (Ubuntu/Debian)
```bash
# Update package repositories
sudo apt-get update && sudo apt-get install -y ca-certificates curl gnupg git

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker engine and compose plugin
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Allow current user to run Docker without sudo
sudo usermod -aG docker $USER
newgrp docker
```

### Configure System Limits for Elasticsearch
Elasticsearch requires `vm.max_map_count` to be at least `262144`:
```bash
# Apply temporarily
sudo sysctl -w vm.max_map_count=262144

# Persist across reboots
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.d/99-elasticsearch.conf
sudo sysctl --system
```

---

## 3. Clone Repository & Initialize Submodules

Clone the repository and recursively initialize all Git submodules:

```bash
git clone --recurse-submodules https://github.com/semantic-croissant/semantic-croissant.git
cd semantic-croissant

# If already cloned without submodules:
git submodule update --init --recursive
```

---

## 4. Build Custom Local Docker Images

Some microservices in the stack are built from local source rather than pulled from public registries:

### A. DDI-CDI Studio (`ddicdi-studio:latest`)
```bash
cd tools/DDICDI_generator_gen2
docker build -t ddicdi-studio:latest .
cd ../..
```

### B. MinIO Base Image (if pulling `minio/minio:latest` is restricted)
Docker Compose defaults to the unrestricted public mirror `cgr.dev/chainguard/minio:latest`.

If you prefer using the official Docker Hub image or a local archive, you can::
1. Override via environment variable `MINIO_IMAGE=minio/minio:latest`
2. Or load from a bundled tarball if available:
```bash
if [ -f "minio-image.tar.gz" ]; then
    docker load -i minio-image.tar.gz
fi
```
3. Or pull and retag the unrestricted Chainguard mirror as standard MinIO:
```bash
docker pull cgr.dev/chainguard/minio:latest
docker tag cgr.dev/chainguard/minio:latest minio/minio:latest
```

### C. Build the Profile API Image (Optional)
Docker Compose automatically builds `api-default` and `default-converters` when using the `default` profile. If building manually for a custom profile (`api-<PROFILE_NAME>`):
```bash
# For default local profile:
docker build -t api-default api/

# For a custom profile (e.g., dvneurope, ca4eosc, codata):
docker build -t api-dvneurope api/
```

---

## 5. Configuration & Environment Profiles

Deployments are isolated via profile environment files located in `profiles/*.env`.

### Available Profiles
- `default.env` (Default fully local setup)
- `dvneurope.env` (Dataverse Europe configuration)
- `ca4eosc.env` (Climate-Adapt4EOSC project)
- `cdif4eosc.env` (CDIF4EOSC project)
- `codata.env` / `codata-dev.env` (CODATA deployment)

### Review and Edit Profile Settings
Select your target profile (e.g. `profiles/dvneurope.env` or `profiles/croissant-live.env`) and adjust settings:

```bash
# Core endpoints and external bindings
HOST=https://your-domain.org
MCP_DOMAIN=your-domain.org
IP=0.0.0.0

# LLM / Ollama Backend
OLLAMA_HOST=http://your-ollama-host:11434
OLLAMA_DEFAULT_MODEL=gemma4:e2b

# Port Allocation (Ensure no port conflicts on the host)
QLEVER_SERVER_PORT=7011
QLEVER_UI_PORT=7055
ES_HOST=http://localhost:9201
API_PORT=7013
MCP_PORT=7115
MINIO_API_PORT=9055
MINIO_CONSOLE_PORT=9057
CONVERTERS_PORT=8082
DDI_CDI_PORT=8083

# Storage Volumes Directory
VOLUME_DIR=./volumes
```

---

## 6. Launching the Services

Run Docker Compose with the desired profile and env-file:

### Example: Starting the `dvneurope` Profile
```bash
docker compose --env-file profiles/dvneurope.env -p dvneurope --profile dvneurope up -d
```

### Example: Starting the Default Local Profile (`default.env`)
```bash
# Launch the full local stack (builds api-default and default-converters automatically)
docker-compose --profile ./profiles/default.env up -d
```

---

## 7. Verifying Deployment & Service Health

Check status of the containers:
```bash
docker compose -p dvneurope ps
```

All services should display `Up` / `healthy`:
| Service | Container Name | Description | Default Port | Health Check |
|---|---|---|---|---|
| `init` | `<profile>-init` | Chowns volume data for users `65534` & `1000` | — | Exits successfully |
| `server` | `<profile>-server` | QLever SPARQL backend | `7011` | `curl http://localhost:7011` |
| `ui` | `<profile>-ui` | QLever Query Web UI | `7012` / `7055` | Open in browser |
| `elasticsearch` | `<profile>-elasticsearch`| Full-Text Search Engine | `9200` / `9201` | `curl http://localhost:9201/_cluster/health` |
| `minio` | `<profile>-minio` | S3 Vault Storage & Console | `9055` (API), `9057` (Console) | Open `:9057` in browser |
| `api` | `<profile>-api` | FastAPI backend & UI portal | `7013` | `curl http://localhost:7013/api/health` |
| `mcp` | `<profile>-mcp` | MCP server (SSE & stdio) | `7115` | `curl http://localhost:7115/sse` |
| `converters` | `<profile>-converters` | CDIF / Croissant conversion service | `8082` | `curl http://localhost:8082/api/health` |
| `ddicdi` | `<profile>-ddicdi` | DDI-CDI Studio tool | `8083` | `curl http://localhost:8083/api/health` |

---

## 8. Common Maintenance & Management Commands

### Viewing Logs
```bash
# Tail logs for all services in profile
docker compose -p dvneurope logs -f

# Tail logs for a specific service (e.g. api or mcp)
docker compose -p dvneurope logs -f api
docker compose -p dvneurope logs -f mcp
```

### Rebuilding a Service after Code Changes
```bash
# If modifying api/ or api/mcp_server.py:
docker build -t api-dvneurope api/
docker compose --env-file profiles/dvneurope.env -p dvneurope restart api mcp

# If modifying tools/converters:
docker compose --env-file profiles/dvneurope.env -p dvneurope up -d --build converters
```

### Stopping the Stack
```bash
docker compose --env-file profiles/dvneurope.env -p dvneurope --profile dvneurope down
```

---

## 9. Troubleshooting

1. **Permission Denied on `/data/...` inside containers**
   - The `init` container fixes volume permissions upon startup (`chown -R 65534:0` for QLever, `chown -R 1000:0` for Elasticsearch & MinIO). Ensure host directories under `./volumes/<profile>` or `./qlever-tests/volumes` are readable/writable by Docker.

2. **Pull Access Denied on `ddicdi-studio:latest`**
   - Build it locally first: `docker build -t ddicdi-studio:latest tools/DDICDI_generator_gen2`.

3. **Elasticsearch Fails to Start (`max virtual memory areas vm.max_map_count [65530] is too low`)**
   - Run `sudo sysctl -w vm.max_map_count=262144`.

4. **MCP Connection Fails**
   - Check that `api` and `elasticsearch` are fully healthy before `mcp` connects.
   - MCP SSE endpoint is at `http://<HOST>:<MCP_PORT>/sse`.

