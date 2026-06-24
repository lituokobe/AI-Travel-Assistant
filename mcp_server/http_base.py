from contextlib import asynccontextmanager
import httpx
from fastmcp import FastMCP

from mcp_server.server_config import MCP_API_BASE_URL


# The dict returned by lifespan will be passed to each tool function via `ctx.request_context.lifespan_context``
# avoiding manual shut down.

@asynccontextmanager
async def mcp_lifespan(server: FastMCP):
    """
    FastMCP life span management: initiate/shut down http client

    Args:
        server: FastMCP instance
    """
    # Create HTTP client（connection pool）
    http_client = httpx.AsyncClient(
        base_url=MCP_API_BASE_URL,
        timeout=30.0,
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
    )
    # http_client.put()
    # Save http_client to lifespan_context，which tool functions will get from ctx
    yield {"http_client": http_client}

    # Clean the resource upon closer
    await http_client.aclose()