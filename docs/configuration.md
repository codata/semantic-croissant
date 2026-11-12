# Configuration: Volumes, Profiles and Ollama Endpoints

## Volume Parameterization
By default, the Docker compose configuration uses volumes located at `./qlever-tests/volumes` and raw data from `./qlever-tests/data`.

You can override these directories by providing environment variables before running docker-compose:

```bash
VOLUME_DIR=/path/to/my/volumes DATA_DIR=/path/to/my/data docker-compose --profile ./profiles/default.env up -d
```

## Profiles
The infrastructure supports running multiple independent instances of Semantic Croissant concurrently on the same machine by using isolated profiles. Environment variables (such as port mappings and `DATA_DIR`) for each profile are stored in the `profiles/` directory (e.g., `profiles/default.env`, `profiles/codata.env`, `profiles/cdif4eosc.env`, `profiles/ca4eosc.env`).

For the default local setup, simply run:
```bash
docker-compose --profile ./profiles/default.env up -d
```

To build and run a specific profile (for example, `ca4eosc`), you must pass the `--env-file` flag pointing to the profile's configuration file and set the `PROFILE_NAME` variable.

1. Build the profile-specific API image:
   ```bash
   docker build -t api-ca4eosc api/
   ```

2. Start the profile using Docker Compose:
   ```bash
   PROFILE_NAME=ca4eosc docker compose --env-file profiles/ca4eosc.env -p ca4eosc --profile ca4eosc up -d
   ```

Each profile is fully sandboxed, ensuring that QLever index data, Elasticsearch volumes, and Minio objects are kept in dedicated subdirectories based on the profile name (e.g., `./qlever-tests/volumes/ca4eosc/` and `./qlever-tests/data/ca4eosc/`).

## Configuring Custom Ollama Inference Endpoints

By default, the Semantic Croissant stack connects to the Codata AI Gateway (`https://mcp.dev.codata.org/gateway`) to leverage models like `gemma4:31b-cloud`. However, you can easily configure the infrastructure to use your own self-hosted or local Ollama instance.

### 1. Connecting a Local Ollama Instance to Docker
If you are running Ollama locally on your host machine (e.g., Mac or Windows via Docker Desktop), the Docker containers cannot access it using `localhost` because `localhost` refers to the container itself. 

Instead, you must point `OLLAMA_HOST` to the host bridge network:
- **Mac / Windows:** Use `http://host.docker.internal:11434`
- **Linux:** Use the IP address of your `docker0` bridge (often `http://172.17.0.1:11434`) or bind Ollama to your machine's LAN IP.

### 2. Updating Profile Variables
To apply this change globally to your running API containers and UI, edit your target environment profile file (e.g., `profiles/ca4eosc.env` or `profiles/croissant-live.env`) and update the corresponding variables:

```env
OLLAMA_HOST=http://host.docker.internal:11434
# If your custom Ollama instance doesn't require an API key, you can leave this blank
OLLAMA_API_KEY=
```

After updating the `.env` profile, recreate the API container so it picks up the new variables:
```bash
PROFILE_NAME=ca4eosc docker compose --env-file profiles/ca4eosc.env -p ca4eosc --profile ca4eosc up -d --force-recreate
```

### 3. Usage in Scripts
When running CLI tools like `url_to_croissant.py` or `test_qa_accuracy.py` locally from your host machine (outside of Docker), you can connect to your local Ollama instance normally via standard environment variables:

```bash
OLLAMA_HOST="http://127.0.0.1:11434" python3 convertors/url_to_croissant.py "https://example.com"
```

### 4. Using Models from Ollama.com
Ollama.com does not offer a cloud-hosted inference API. Instead, it serves as a public registry for models that you download and run locally.

To use models from ollama.com in Semantic Croissant:
1. Ensure your local Ollama instance is running.
2. Open your host machine's terminal and pull the model from the Ollama library:
   ```bash
   ollama pull llama3.2
   ```
3. Once downloaded, the model will automatically appear in the drop-down menu in the Semantic Croissant UI as long as your `OLLAMA_HOST` is correctly pointing to your local instance (as described in Step 2).
