from fastmcp import FastMCP

from mcp_server.http_base import mcp_lifespan
from mcp_server.server_config import MCP_HOST, MCP_PORT, MCP_PATH
from mcp_server.tools.car_tools import register_car_tools
from mcp_server.tools.flights_tools import register_flights_tools
from mcp_server.tools.hotels_tools import register_hotels_tools
from mcp_server.tools.trip_tools import register_trip_tools

# Create FastMCP instance with life span management
mcp = FastMCP(
    name="Travel-Assistant-MCP-Server",
    instructions="Support visiting by group",
    version="1.0.0",
    lifespan=mcp_lifespan
)


# Register all the group
register_flights_tools(mcp)
register_car_tools(mcp)
register_hotels_tools(mcp)
register_trip_tools(mcp)


def main():

    # start Streamable HTTP service
    mcp.run(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
        path=MCP_PATH
    )
    # Attention：run() will block，and `lifespan` will automatically clear the resource when the service shuts down


if __name__ == "__main__":
    main()