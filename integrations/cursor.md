# Connecting Semantic Croissant MCP with Cursor

Cursor IDE has native support for the Model Context Protocol (MCP), allowing its AI assistant to seamlessly use tools provided by your Semantic Croissant deployment.

You can connect your deployed MCP Server-Sent Events (SSE) endpoint to Cursor in just a few steps.

## Setup Instructions

1. **Open Cursor Settings**
   Open the settings in Cursor (using `Cmd + ,` on Mac or `Ctrl + ,` on Windows/Linux).

2. **Navigate to MCP Servers**
   In the settings sidebar, go to **Features** and scroll down to the **MCP Servers** section.

3. **Add a New MCP Server**
   Click the **+ Add New MCP Server** button.

4. **Configure the Connection**
   Fill out the configuration fields with the following details:
   - **Name**: `Semantic Croissant` (or any name you prefer)
   - **Type**: Select **`sse`** from the dropdown menu.
   - **URL**: `https://ai.codata.org/sse` (If you are running locally, use `http://localhost:7070/sse` instead).

5. **Save and Connect**
   Click **Save**. Cursor will automatically connect to the SSE endpoint, discover all available tools (like `read_vault_article`, `extract_variables_from_croissant`, etc.), and display a green indicator when the connection is successful.

## Using the Tools

Once connected, you can simply ask Cursor's AI (using `Cmd + L` or `Cmd + K`) to perform tasks using the dataset. For example:
- *"Use the Semantic Croissant tool to fetch the dataset metadata for https://doi.org/10.7910/DVN/PUWWV9"*
- *"Can you read the vault article X and summarize it?"*

Cursor's agent will automatically know when to call these tools to fulfill your prompt!

## Using Semantic Croissant for LLM Inference

In addition to providing tools, the Semantic Croissant deployment acts as an API gateway that can provide open-source LLM inference. You can configure Cursor to use this gateway instead of paying for OpenAI models.

1. **Open Cursor Settings**
   Go to Cursor settings (`Cmd + ,` or `Ctrl + ,`).

2. **Navigate to Models Configuration**
   In the settings sidebar, go to **General** > **Models** (or **Features** > **Models** depending on your Cursor version).

3. **Override the OpenAI Base URL**
   - Toggle **Override OpenAI Base URL**.
   - Set the Base URL to: `https://ai.codata.org/gateway/v1` (or `http://localhost:7070/gateway/v1` for local deployments).
   - If your gateway is secured with an API key (configured in `gateway_config.json`), enter that key in the **OpenAI API Key** field.

4. **Select or Add Custom Models**
   - In the same Models settings area, you can add custom model names by clicking **+ Add model**.
   - Type in the names of the open-source models available on your backend (e.g., `deepseek-r1:14b`, `gpt-oss:latest`, or `gemma4:e2b`) and enable them.
   - You can now select these models from the dropdown when chatting with Cursor (using `Cmd + L`). Cursor will route all LLM requests through your custom gateway!
