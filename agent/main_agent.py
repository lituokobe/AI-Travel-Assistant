import asyncio

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StoreBackend
from langchain_core.runnables import RunnableConfig

from agent.backends.sandbox_setup import setup_sandbox
from agent.config import SANDBOX_CONFIG, LOCAL_AGENTS_MD, STORE, SKILLS_STORE_NAMESPACE, DOWNLOAD_DIR, SUMMARY_MODEL
from agent.logger import logger
from agent.middleware_config import create_analyst_middleware, create_order_middleware
from agent.subagents.loader import load_subagent_configs
from agent.tools.assign_skill import create_assign_skill_tool
from agent.tools.download_sandbox_file import create_download_tool
from agent.tools.hitl_tools import request_travel_info
from agent.tools.mcp_client import load_mcp_tools
from agent.tools.web_search import web_search


async def create_main_agent(
    config: RunnableConfig|None = None,
    *,
    sandbox_id: str|None = None,
):
    """
    async graph factory to create main travel agent.

    When called, execute complete 11-stage streamline:
    1. Sandbox configuration
    2. Write AGENTS.md to sandbox
    3. CompositeBackend
    4. Load MCP tools
    5. Build tool pool
    6. Load Agent YAML
    7. subagents' middleware
    8. Interpret tool names
    9. main agent's middleware
    10. create_deep_agent()

    Args:
        config: LangGraph RunnableConfig, injected by langgraph
        sandbox_id: optional, reuse existing sandbox id. create new one when None

    Returns:
        Compiled LangGraph StateGraph，callable with .ainvoke() / .astream()。
    """
    logger.info("=== Start to build AI travel assistant ===")

    # ---- Phase 1: Sandbox configuration ----
    logger.info("Phase 1/11: Sandbox configuration...")
    try:
        sandbox_backend = setup_sandbox(SANDBOX_CONFIG, sandbox_id=sandbox_id)
    except Exception as e:
        e_m = f"Sandbox configuration failed: {e}"
        logger.error(e_m)
        raise RuntimeError(e_m)

    # ---- Phase 2: Write AGENTS.md to sandbox ----
    # AGENTS.md in sandbox will be hit by CompositeBackend routing of default
    logger.info("Phase 2/11: Write AGENTS.md to sandbox...")
    ag_md_content = LOCAL_AGENTS_MD.read_text(encoding="utf-8")
    sandbox_backend.upload_files([("/AGENTS.md", ag_md_content.encode("utf-8"))])
    logger.info("  AGENTS.md is uploaded to sandbox")

    # ---- Phase 3: CompositeBackend ----
    # /AGENTS.md          → default routing to sandbox
    # /memories/          → StoreBackend (isolate user preference by user_id)
    # /persisted-skills/  → StoreBackend (organize skills by Agent scope)
    # Other paths (temp files, file execution) save in sandbox
    logger.info("Phase 3: Configure CompositeBackend (memories + persisted-skills → Store)...")
    logger.info(f"🔍 DEBUG: STORE type={type(STORE)}, sandbox_id={sandbox_id}")

    backend = lambda rt: CompositeBackend(
        default=sandbox_backend,
        routes={
            "/memories/": StoreBackend(
                runtime=rt,
                namespace=lambda rt: (getattr(rt.runtime.context, 'user_id', 'lituokobe'),),
            ),
            "/persisted-skills/": StoreBackend(
                runtime=rt,
                namespace=lambda rt: SKILLS_STORE_NAMESPACE,
            ),
        },
    )

    # 🔍 TEMP: Test the backend creation immediately
    """
    type() is to class what lambda is to def
    Both are the low-level, dynamic, programmatic ways to create Python objects — while class/def are the high-level, readable, declarative syntax sugar.
    """
    try:
        test_rt = type(
            'MockRuntime',
            (),
            {
                'runtime': type(
                    'MockCtx',
                    (),
                    {'context': type(
                        'MockUser',
                        (),
                        {'user_id': 'test'}
                    )()
                     })()
            }
        )()
        test_backend = backend(test_rt)
        logger.info(f"✅ CompositeBackend created successfully: {test_backend}")
    except Exception as e:
        logger.error(f"❌ CompositeBackend creation failed: {e}", exc_info=True)
        raise

    # ---- Phase 4: Load MCP tools ----
    logger.info("Phase 4/11: Load MCP tools...")
    try:
        all_tools, flights_tools, car_tools, hotels_tools, trip_tools = (
            await load_mcp_tools()
        )
    except Exception as e:
        e_m = f"MCP tools failed to load: {e}"
        logger.error(e_m)
        raise RuntimeError(e_m)

    # ---- Phase 4.5: create skill management tool ----
    assign_skill = create_assign_skill_tool(
        sandbox_backend,
        store=STORE,
        skills_namespace=SKILLS_STORE_NAMESPACE,
    )
    download_sandbox_file = create_download_tool(sandbox_backend, DOWNLOAD_DIR)

    # ---- Phase 5: Build tool pool ----
    logger.info("Phase 5/10: Build tool pool...")
    available_tools = (
        list(flights_tools)
        + list(car_tools)
        + list(hotels_tools)
        + list(trip_tools)
        + [web_search]
        + [request_travel_info]
        + [assign_skill]
        + [download_sandbox_file]
    )
    logger.info(f"  Tool pool: {len(available_tools)} tools")

    # ---- Phase 6: Load Agent YAML ----
    logger.info("Phase 6/10: Load Agent YAML...")
    raw_configs = load_subagent_configs()
    if not raw_configs:
        logger.warning("  No configurations of Sub-Agent found, Agent will run without Sub-Agent")
    else:
        logger.info(f"  {len(raw_configs)} configurations of Sub-Agent loaded")

    # ---- Phase 7: subagents' middleware ----
    logger.info("Phase 7/10: subagents' middleware...")
    extra_middleware = {
        "procurement-analyst": create_analyst_middleware(SUMMARY_MODEL, backend),
        "procurement-order": create_order_middleware(),
    }

    # ---- Phase 8: Interpret tool names ----
    logger.info("Phase 8/10: Interpret tool names...")
    subagents = resolve_subagent_tools(
        raw_configs,
        available_tools,
        extra_middleware=extra_middleware,
    )
    logger.info(f"  已解析 {len(subagents)} 个子 Agent")

    # ---- Phase 9: main agent's middleware ----
    logger.info("Phase 9/10: main agent's middleware...")
    main_middleware = [
        ContextInjectionMiddleware(),
        SkillsSyncMiddleware(sandbox_backend),
        UserSkillsRestoreMiddleware(sandbox_backend, SKILLS_STORE_NAMESPACE),
        build_summarization_middleware(backend, SUMMARY_MODEL),
        MemoryUpdateMiddleware(model=SUMMARY_MODEL),
        ModelCallLimitMiddleware(run_limit=50),
        ToolCallLimitMiddleware(run_limit=200),
    ]

    # ---- Phase 10: create_deep_agent() ----
    logger.info("Phase 10/10: Create Deep Agent...")
    agent_graph = create_deep_agent(
        model=MAIN_MODEL,
        system_prompt=system_prompt,
        skills=["/skills/main/"],
        memory=[AGENTS_MD_FILENAME],
        tools=[web_search, assign_skill, download_sandbox_file],
        subagents=subagents,
        middleware=main_middleware,
        backend=backend,
        store=STORE,  # 数据保持到哪里？
        checkpointer=CHECKPOINTER,  # 上下文管理和持久化（mongoDB里面）
        context_schema=ProcurementContext,  # 接受运行时数据的格式
    )

    logger.info("=== AI Travel Assistant is successfully created ===")
    return agent_graph


# agent = asyncio.run(create_main_agent(sandbox_id='8b5d68e6-b6f4-4bde-823d-1fb510881581'))
# agent = asyncio.run(create_main_agent())


# ============================================================
# Agent 懒加载代理（兼容同步/异步两种初始化场景）
# ============================================================

async def _create_agent():
    """创建 Agent 实例（供 _AgentProxy 调用）"""
    return await create_main_agent()


class _AgentProxy:
    """
    懒加载 Agent 代理类

    兼容以下两种使用场景：
    1. 同步环境（如 agent_test.py 控制台）：在模块导入后、事件循环启动前初始化
    2. 异步环境（如 FastAPI 后端）：通过 get_agent_async() 在事件循环中初始化

    当直接访问 agent 对象的属性/方法时，代理会自动触发初始化并委托调用。
    """

    def __init__(self):
        self._agent = None

    @property
    def _is_initialized(self):
        """检查底层 agent 是否已初始化"""
        return self._agent is not None

    def _ensure_initialized(self):
        """
        确保 agent 已初始化（同步方式）

        如果没有运行中的事件循环，使用 asyncio.run() 创建 agent。
        如果事件循环正在运行，抛出 RuntimeError 提示使用 get_agent_async()。
        """
        if self._agent is not None:
            return self._agent

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError(
                    "Agent 尚未初始化且当前在事件循环中，"
                    "请使用 await get_agent_async() 获取 agent"
                )
        except RuntimeError as e:
            if "Agent 尚未初始化" in str(e):
                raise
            # 没有事件循环，继续初始化

        self._agent = asyncio.run(_create_agent())
        return self._agent

    def __getattr__(self, name):
        return getattr(self._ensure_initialized(), name)

    def __repr__(self):
        if self._agent is None:
            return "<AgentProxy (not initialized)>"
        return repr(self._agent)


# agent 实例，初始化为懒加载代理，由 get_agent() / get_agent_async() 函数触发初始化
agent = _AgentProxy()


def get_agent():
    """
    获取 agent 实例，懒加载方式（同步）

    如果 agent 尚未初始化，则同步创建它。
    注意：不能在运行中的事件循环内调用此函数。

    Returns:
        CompiledStateGraph: Agent 实例
    """
    global agent
    if isinstance(agent, _AgentProxy):
        if agent._is_initialized:
            return agent._agent
        return agent._ensure_initialized()
    return agent


async def get_agent_async():
    """
    异步获取 agent 实例，懒加载方式

    适用于在事件循环中运行时调用（如 FastAPI 的 lifespan）。
    如果 agent 已通过 get_agent() 同步初始化，则直接返回。

    Returns:
        CompiledStateGraph: Agent 实例
    """
    global agent
    if isinstance(agent, _AgentProxy):
        if agent._is_initialized:
            return agent._agent
        agent._agent = await _create_agent()
        return agent._agent
    return agent