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

# tool grouping based on prefixes
FLIGHTS_TOOL_PREFIXES = ("flights_", )
CAR_TOOL_PREFIXES = ("car_",)
HOTELS_TOOL_PREFIXES = ("hotels_",)
ACTIVITY_TOOL_PREFIXES = ("activity_",)


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

    logger.info("Connecting to MCP Server...")
    mcp_client = MultiServerMCPClient(server_config)

    # Load business tools from MCP Server
    travel_assistant_tools = await mcp_client.get_tools(server_name="travel-assistant-api")
    logger.info(f"Loaded {len(travel_assistant_tools )} tools from MCP server")
    # Merge all tools
    all_tools = list(travel_assistant_tools)

    # Group business tools by prefix
    flights_tools = [
        t for t in travel_assistant_tools
        if t.name.startswith(FLIGHTS_TOOL_PREFIXES)
    ]

    car_tools = [
        t for t in travel_assistant_tools
        if t.name.startswith(CAR_TOOL_PREFIXES)
    ]

    hotels_tools = [
        t for t in travel_assistant_tools
        if t.name.startswith(HOTELS_TOOL_PREFIXES)
    ]

    activity_tools = [
        t for t in travel_assistant_tools
        if t.name.startswith(ACTIVITY_TOOL_PREFIXES)
    ]


    logger.info(
        f"Tools are grouped: "
        f"Flights tools: {len(flights_tools)} , "
        f"Car tools: {len(car_tools)} , "
        f"Hotels tools: {len(hotels_tools)} , "
        f"Activity tools: {len(activity_tools)} "
    )

    return all_tools, flights_tools, car_tools, hotels_tools, activity_tools
