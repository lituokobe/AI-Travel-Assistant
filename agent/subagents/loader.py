"""
Sub-agent YAML configuration loader.

Reads sub-agent definitions from a YAML configuration directory and converts
them into the SubAgent dict format required by DeepAgents' create_deep_agent().

Usage:
    from agent.subagents.loader import load_subagent_configs, resolve_subagent_tools

    # 1. Load raw configurations (tools are lists of string names)
    raw_configs = load_subagent_configs()

    # 2. Match with MCP tools and resolve them into callable tool objects
    subagents = resolve_subagent_tools(raw_configs, all_mcp_tools)
"""
from __future__ import annotations

from pathlib import Path
import yaml
from agent.logger import logger
from agent.tools.hitl_tools import request_travel_info

# YAML configuration file directory
CONFIGS_DIR = Path(__file__).parent / "configs"

# Tools automatically injected into every sub-agent.
# Listed here once so each sub-agent YAML does not have to repeat them.
# Currently this is the human-in-the-loop escalation tool shared by all
# booking specialists.
COMMON_SUBAGENT_TOOLS = [request_travel_info]


def load_subagent_configs(
    configs_dir: Path|None = None,
) -> list[dict]:
    """
    Load all .yaml sub-agent configuration files in the specified directory.

    Top-level structure of each YAML file:
        name: str               # Required — Unique name of the sub-agent
        description: str        # Required — Description for the main agent's decision-making
        system_prompt: str      # Required — System prompt for the sub-agent
        tools: list[str]        # Required — List of tool names (resolved at runtime)
        model: str              # Optional — Model identifier
        skills: list[str]       # Optional — List of skill paths

    Args:
        configs_dir: Configuration file directory, defaults to CONFIGS_DIR.

    Returns:
        A list of SubAgent configuration dictionaries, where the tools field
        currently contains string names.
    """
    if configs_dir is None:
        configs_dir = CONFIGS_DIR

    configs: list[dict] = []

    if not configs_dir.exists():
        logger.warning(f"Sub-agent configuration directory does not exist: {configs_dir}")
        return configs

    # Explicitly type the list so the IDE knows yaml_file is a Path
    yaml_files: list[Path] = sorted(configs_dir.glob("*.yaml"))

    for yaml_file in yaml_files:
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML file: {yaml_file} — {e}")
            continue
        except Exception as e:
            logger.error(f"Failed to read file: {yaml_file} — {e}")
            continue

        # Validate required fields
        missing = _validate_subagent_config(data)
        if missing:
            logger.error(
                f"{yaml_file.name} is missing required fields: {', '.join(missing)}"
            )
            continue

        configs.append(data)
        logger.info(f"Loaded sub-agent configuration: {data['name']} <- {yaml_file.name}")

    return configs


def resolve_subagent_tools(
    configs: list[dict],
    available_tools: list,
    extra_middleware: dict[str, list] | None = None,
) -> list[dict]:
    """
    Resolve tool name strings in the YAML configuration into actual callable tool objects.

    Matching rules:
    - Each string in the YAML 'tools' list must EXACTLY match the .name attribute of
      an available tool. This is stricter than the previous substring match and avoids
      accidental cross-matches between similarly named tools (e.g. a 'car_' pattern
      silently matching a 'rental_car_*' tool).
    - Tools listed in COMMON_SUBAGENT_TOOLS (e.g. request_travel_info) are appended
      automatically to every sub-agent and do not need to be declared in YAML.

    Args:
        configs: List of raw configurations returned by load_subagent_configs().
        available_tools: List of available tool objects (from the MCP client).
        extra_middleware: Additional middleware for sub-agents; keys are sub-agent
                          names, values are lists of middleware instances.

    Returns:
        A list of SubAgent dictionaries that can be directly passed to
        create_deep_agent(subagents=...).
    """
    if extra_middleware is None:
        extra_middleware = {}
    # Build an index of tool name -> tool object
    tool_index: dict[str, object] = {}
    for t in available_tools:
        name = getattr(t, "name", None)
        if isinstance(name, str):
            tool_index[name] = t

    subagents: list[dict] = []

    for config in configs:
        tool_names = config.get("tools", [])
        resolved_tools = []

        for pattern in tool_names:
            # Exact match only — fail loudly with a warning instead of
            # silently picking up unrelated tools.
            tool_obj = tool_index.get(pattern)
            if tool_obj is not None:
                resolved_tools.append(tool_obj)
            else:
                logger.warning(
                    f"Sub-agent '{config['name']}': "
                    f"Tool '{pattern}' did not exactly match any available tool"
                )

        # Append shared tools that every sub-agent needs (HITL escalation, etc.)
        for common_tool in COMMON_SUBAGENT_TOOLS:
            resolved_tools.append(common_tool)

        # Deduplicate (preserve order)
        seen = set()
        unique_tools = []
        for t in resolved_tools:
            name = getattr(t, "name", id(t))
            if name not in seen:
                seen.add(name)
                unique_tools.append(t)

        subagent: dict = {
            "name": config["name"],
            "description": config["description"].replace("\n", " ").strip(),
            "system_prompt": config["system_prompt"],
            "tools": unique_tools,
        }

        # Optional fields
        if config.get("model"):
            subagent["model"] = config["model"]

        if config.get("skills"):
            subagent["skills"] = config["skills"]

        if config.get("interrupt_on"):
            subagent["interrupt_on"] = config["interrupt_on"]

        # Merge extra middleware
        agent_middleware = list(config.get("middleware", []))
        if config["name"] in extra_middleware:
            agent_middleware.extend(extra_middleware[config["name"]])
        if agent_middleware:
            subagent["middleware"] = agent_middleware

        common_names = [getattr(t, "name", "?") for t in COMMON_SUBAGENT_TOOLS]
        subagents.append(subagent)
        logger.info(
            f"Sub-agent '{config['name']}' resolved: "
            f"{len(unique_tools)} tools "
            f"(incl. common: {common_names}), "
            f"{len(config.get('skills', []))} skills"
        )

    return subagents


def _validate_subagent_config(data: dict) -> list[str]:
    """
    Validate required fields for SubAgent configuration.

    Returns:
        A list of missing field names (an empty list indicates validation passed).
    """
    required = ["name", "description", "system_prompt", "tools"]
    missing = [f for f in required if f not in data or data[f] is None]

    # tools must be a non-empty list
    if "tools" in data:
        tools = data["tools"]
        if not isinstance(tools, list) or len(tools) == 0:
            missing.append("tools (must be a non-empty list)")

    # system_prompt cannot be an empty string
    if "system_prompt" in data:
        sp = data["system_prompt"]
        if not isinstance(sp, str) or not sp.strip():
            missing.append("system_prompt (must be a non-empty string)")

    return missing