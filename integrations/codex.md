# Connecting Semantic Croissant with Codex & OpenAI-Compatible Clients

You can use the Semantic Croissant deployment as a drop-in replacement for OpenAI endpoints to serve AI tools and inference to Codex, Sourcegraph Cody, or any OpenAI-compatible client.

## Using Semantic Croissant for Inference

Since Semantic Croissant intercepts requests at the gateway layer, you can route standard API traffic through it to utilize your hosted open-source models.

1. **Override the API Base URL**
   In your client settings, locate the field for the **OpenAI Base URL** or **API Endpoint** and set it to:
   - **Base URL**: `https://ai.codata.org/gateway/v1` (or `http://localhost:7070/gateway/v1` for local deployments).

2. **API Key Configuration**
   - If your `gateway_config.json` has security enabled, enter your custom API key in the OpenAI API Key field.
   - Otherwise, you can enter any placeholder string (e.g., `sk-dummy`).

3. **Select Your Models**
   The gateway exposes models dynamically based on what is deployed in your backend. When your client fetches the model list, it will present the available open-source models (e.g., `gpt-oss:latest` or `deepseek-r1:14b`).
   
   Select the desired model and all your Codex/completion requests will be securely routed to your private infrastructure instead of OpenAI!

## Accessing Tools & Function Calling

If your client supports OpenAI's tool-calling (function calling) format, Semantic Croissant will automatically expose the same MCP tools (like `read_vault_article` or `extract_variables_from_croissant`) as standard OpenAI functions!

When you prompt the agent to perform an action related to your dataset or vault, it will invoke the function, and the API gateway will seamlessly translate that into a native MCP tool call on the backend, returning the results directly to your prompt context.
