# Connecting Semantic Croissant with Claude

You can integrate your Semantic Croissant deployment with Claude in two ways: via the official Claude Desktop app for tool access, or by pointing any Anthropic-compatible client to the Croissant API Gateway for inference.

## 1. Connecting Claude Desktop via MCP

Claude Desktop natively supports the Model Context Protocol (MCP) to access external tools. 

1. **Open Claude Desktop Configuration**
   Open your Claude Desktop config file:
   - **Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

2. **Add the MCP Server**
   Since Claude Desktop currently requires standard stdio execution (it does not natively support remote SSE endpoints without a proxy script), you can configure it to run the local docker container:
   
   ```json
   {
     "mcpServers": {
       "semantic-croissant": {
         "command": "docker",
         "args": ["exec", "-i", "mcp-croissant-live", "python", "/app/mcp_server.py"]
       }
     }
   }
   ```
   *(Note: If you want to connect remotely to `https://ai.codata.org/sse` from Claude Desktop, you can use the community `mcp-sse-bridge` npm package).*

## 2. Using Semantic Croissant for Claude Inference

Semantic Croissant acts as an Anthropic-compatible API gateway. It dynamically translates requests meant for Anthropic's Claude models to your local open-source models (like `deepseek-r1:14b` or `gpt-oss:latest`) while maintaining tool support!

1. **Configure your Anthropic Client**
   Point your client's API Base URL to the Semantic Croissant Gateway:
   - **API Base URL**: `https://ai.codata.org/gateway` (or `http://localhost:7070/gateway`)

2. **Model Selection**
   When your client fetches available models (via `/v1/models`), the gateway will automatically inject the names of your available open-source models under the guise of official Claude model IDs. 
   
   For example, you'll see options like:
   - `Claude 3.5 Sonnet (Inference: deepseek-r1:14b)`
   
   Simply select one of these models. Your client will think it's talking to Claude, but the Semantic Croissant gateway will securely proxy the request to your selected open-source model!
