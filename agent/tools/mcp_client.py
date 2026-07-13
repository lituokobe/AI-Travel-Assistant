"""
MCP tools client.

Connects to all MCP Servers at Agent startup, loads all MCP tools,
and groups them for assignment to different sub-agents.

Usage:
    from agent.tools.mcp_client import load_mcp_tools

    all_tools, flights_tools, car_tools, hotels_tools, activity_tools = await load_mcp_tools()
"""

from langchain_mcp_adapters.client import MultiServerMCPClient
from agent.logger import logger

MCP_SERVER_CONFIG = {
    "travel-assistant-api": {
        "url": "http://127.0.0.1:8000/mcp",
        "transport": "streamable_http",
    }
}

# Tool grouping prefixes (one domain per sub-agent).
# str.startswith accepts a single str — keep these as plain strings so the
# intent reads clearly and there is no ambiguity with tuple-of-prefixes.
FLIGHTS_TOOL_PREFIX = "flights_"
CAR_TOOL_PREFIX = "car_"
HOTELS_TOOL_PREFIX = "hotels_"
ACTIVITY_TOOL_PREFIX = "activity_"

# MCP server connection resilience.
_MCP_MAX_ATTEMPTS = 3
_MCP_BACKOFF_BASE_SECONDS = 1.5


async def _load_tools_with_retry(server_config: dict) -> list:
    """Connect to the MCP server and load tools, retrying with exponential backoff.

    Raises:
        RuntimeError: if all attempts fail (server unreachable or returns no tools).
    """
    import asyncio

    last_error: Exception | None = None
    for attempt in range(1, _MCP_MAX_ATTEMPTS + 1):
        try:
            logger.info(
                f"Connecting to MCP Server (attempt {attempt}/{_MCP_MAX_ATTEMPTS})..."
            )
            mcp_client = MultiServerMCPClient(server_config)
            tools = await mcp_client.get_tools(server_name="travel-assistant-api")
            if not tools:
                # No tools usually means the server is up but the tool layer
                # is not ready yet — worth retrying.
                raise RuntimeError("MCP server returned 0 tools")
            return tools
        except Exception as e:
            last_error = e
            logger.warning(f"MCP attempt {attempt} failed: {e}")
            if attempt < _MCP_MAX_ATTEMPTS:
                sleep_for = _MCP_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.info(f"Retrying MCP connection in {sleep_for:.1f}s...")
                await asyncio.sleep(sleep_for)

    raise RuntimeError(
        f"Failed to load MCP tools after {_MCP_MAX_ATTEMPTS} attempts. "
        f"Is the MCP server running at {MCP_SERVER_CONFIG['travel-assistant-api']['url']}? "
        f"Last error: {last_error}"
    )


async def load_mcp_tools(
    server_config: dict | None = None,
) -> tuple[list, list, list, list, list]:
    """
    Connect to all MCP Servers, load all tools, and group them.

    Args:
        server_config: MCP Server connection config; defaults to MCP_SERVER_CONFIG.

    Returns:
        Tuple of (all_tools, flights_tools, car_tools, hotels_tools, activity_tools)
        - all_tools: full list of MCP tools
        - flights_tools: search, book, modify, cancel flights
        - car_tools: search, book, modify, cancel car rentals
        - hotels_tools: search, book, modify, cancel hotel bookings
        - activity_tools: search, book, modify, cancel travel activities
    """
    if server_config is None:
        server_config = MCP_SERVER_CONFIG

    travel_assistant_tools = await _load_tools_with_retry(server_config)
    logger.info(f"Loaded {len(travel_assistant_tools)} tools from MCP server")

    # Merge all tools
    all_tools = list(travel_assistant_tools)

    # Group business tools by prefix
    flights_tools = [
        t for t in travel_assistant_tools
        if t.name.startswith(FLIGHTS_TOOL_PREFIX)
    ]

    car_tools = [
        t for t in travel_assistant_tools
        if t.name.startswith(CAR_TOOL_PREFIX)
    ]

    hotels_tools = [
        t for t in travel_assistant_tools
        if t.name.startswith(HOTELS_TOOL_PREFIX)
    ]

    activity_tools = [
        t for t in travel_assistant_tools
        if t.name.startswith(ACTIVITY_TOOL_PREFIX)
    ]


    logger.info(
        f"Tools are grouped: "
        f"Flights tools: {len(flights_tools)} , "
        f"Car tools: {len(car_tools)} , "
        f"Hotels tools: {len(hotels_tools)} , "
        f"Activity tools: {len(activity_tools)} "
    )

    return all_tools, flights_tools, car_tools, hotels_tools, activity_tools
