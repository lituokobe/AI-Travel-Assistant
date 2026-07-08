# AI Travel Assistant — Start the Service

## 1. Prerequisites

Before launching the assistant, prepare and start the following services:

### Redis (short-term memory / LangGraph checkpointing)

Start Redis Service (mount the data in a local directory):
``` shell
docker run -d \
  --name redis \
  -p 6379:6379 \
  -p 8001:8001 \
  -v ./data/redis-data:/data \
  redis/redis-stack:latest
```

### MongoDB (long-term memory / LangGraph store)

Start MongoDB Service (mount the data in a local directory):
``` shell
docker run -d \
  --name mongodb \
  -p 27017:27017 \
  -v ./data/mongodb-data:/data/db \
  mongo:latest
```

### OpenSandbox (remote code-execution sandbox)

Start Opensandbox service on your host (e.g. Alicloud), then set its address in
your `.env` file:

``` shell
SANDBOX_DOMAIN=http://your-sandbox-host:8080
```

OpenSandbox is required at import time — the app will not start without
`SANDBOX_DOMAIN` set.

### Environment & dependencies

1. Copy `env.example` to `.env` and fill in your keys (at minimum
   `DEEPSEEK_API_KEY`, `TAVILY_API_KEY`, and `SANDBOX_DOMAIN`):
   ``` shell
   cp env.example .env
   ```
2. Install Python dependencies with `uv`:
   ``` shell
   uv sync
   ```

## 2. Ports

The launcher starts three local processes. Their ports:

| Service            | Port  | URL / Notes                      |
| ------------------ | ----- | -------------------------------- |
| Gradio Chat UI     | 7860  | http://localhost:7860            |
| FastAPI Agent API  | 8080  | http://localhost:8080/docs       |
| MCP Tool Server    | 8000  | http://127.0.0.1:8000/mcp        |

External/infrastructure services that must already be running:

| Service   | Port  | Used for                          |
| --------- | ----- | --------------------------------- |
| Redis     | 6379  | Short-term memory (checkpoints)   |
| MongoDB   | 27017 | Long-term memory (store)          |
| OpenSandbox | 8080 (remote) | Code execution sandbox   |

## 3. Start the service

The unified launcher starts everything in order: syncs the local SQLite travel
DB, starts the MCP tool server, the FastAPI agent API, and the Gradio chat UI.
The MCP server is started automatically — you do **not** need to start it
separately.

``` shell
uv run python demo/run_demo.py
```

Once it prints `Demo is running!`, open the chat UI at
http://localhost:7860. Press `Ctrl+C` to stop all services.

Options:

``` shell
uv run python demo/run_demo.py --skip-ui        # API + MCP only, no Gradio UI
uv run python demo/run_demo.py --sync-db-only   # only refresh travel DB dates
uv run python demo/run_demo.py --no-db-sync     # skip DB date sync
```
