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

## 5. Using the LLM for Highlighted Text & Saving to Vault
The Semantic Croissant web interface allows users to seamlessly extract insights from documents using an integrated LLM.

1. **Highlight Text**: Open any document in the Vault viewer and highlight a specific block of text.
2. **Ask AI**: Click the **Ask AI** button that appears in the popup menu.
3. **Select Model & Ask**: Choose an inference model (e.g., from the Codata AI Gateway or your local Ollama instance) and type your question.
4. **Multi-Turn Chat**: After receiving an answer, you can either:
   - **Ask again**: Ask a new question based on the same highlighted context.
   - **Remember this and ask again**: Continue the conversation, passing the entire previous Q&A history back to the LLM.
5. **Save Q&A to Vault**: Once satisfied, click the **Save Q&A** button. This automatically saves the entire context, question, and answer block as a Markdown snippet in the Vault, anchoring it securely to your current Croissant document dataset.
