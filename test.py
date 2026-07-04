import asyncio

from agent.tools.mcp_client import load_mcp_tools
from agent.tools.web_search import web_search

all_tools, flights_tools, car_tools, hotels_tools, activity_tools = asyncio.run(load_mcp_tools())

for t in all_tools:
    name = getattr(t, "name", None)
    print(name)
