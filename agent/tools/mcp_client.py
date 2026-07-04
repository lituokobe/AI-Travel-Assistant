"""
MCP 工具客户端。

在 Agent 启动时连接所有 MCP Server，获取全部 MCP 工具，
并按分组筛选后分配给不同的子 Agent。

使用方式:
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
    连接到所有 MCP Server，加载全部工具并分组。

    Args:
        server_config: MCP Server 连接配置，默认使用 MCP_SERVER_CONFIG。

    Returns:
        (all_tools, flights_tools, car_tools, hotels_tools, activity_tools) 四元组
        - all_tools: 全部 MCP 工具列表
        - flights_tools: 查询、预订、修改、取消航班
        - car_tools: 查询、预订、修改、取消租车
        - hotels_tools: 查询、预订、修改、取消酒店订单
        - activity_tools: 查询、预订、修改、取消旅行活动
    """
    if server_config is None:
        server_config = MCP_SERVER_CONFIG

    logger.info("Connecting to MCP Server...")
    mcp_client = MultiServerMCPClient(server_config)

    # 从 MCP Server 获取业务工具
    travel_assistant_tools = await mcp_client.get_tools(server_name="travel-assistant-api")
    logger.info(f"Loaded {len(travel_assistant_tools )} tools from MCP server")
    # 合并全部工具
    all_tools = list(travel_assistant_tools)

    # 按前缀分组：业务工具
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
