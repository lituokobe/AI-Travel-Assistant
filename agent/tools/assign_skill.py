# src/tools/assign_skill.py
"""
Skill Assignment Tool

Assigns verified skills from /skills/main/ to a specified Agent (main Agent or sub-Agent).
Supports StoreBackend persistence and archive package cleanup.
"""
from __future__ import annotations
from datetime import datetime, timezone
from agent.config import SCOPE_MAP
from langchain_core.tools import tool


def create_assign_skill_tool(sandbox_backend, store, skills_namespace):
    """
    Factory function to create the assign_skill tool.

    Args:
        sandbox_backend: OpenSandboxBackend instance for file operations within the sandbox.
        store: BaseStore instance (from config.STORE) used to persist skills to the StoreBackend.
        skills_namespace: Namespace tuple for skills in the StoreBackend.

    Returns:
        The async assign_skill tool function.
    """

    @tool
    async def assign_skill(skill_name: str, agent_name: str) -> str:
        """
        将已验证的技能分配给指定 Agent（主 Agent 或子 Agent），并持久化到长期存储。

        前提条件：技能已下载/创建到 /skills/main/{skill_name}/ 并通过测试。

        Args:
            skill_name: 技能目录名（如 "web-scraper"）
            agent_name: 目标 Agent：
                - "main" — 分配给主 Agent 自身（技能已就位，直接持久化）
                - "" — 分配给采购分析子 Agent
                - "procurement-order" — 分配给采购订单子 Agent

        Returns:
            分配确认或错误信息。
        Assigns a verified skill to a specified Agent (main Agent or sub-Agent) and persists it to long-term storage.

        Prerequisites: The skill must have been downloaded/created to /skills/main/{skill_name}/ and passed testing.

        Args:
            skill_name: The skill directory name (e.g., "plan-travel").
            agent_name: The target Agent:
                - "main" — Assigns to the main Agent itself (skill is already in place, persists directly).
                - "car-agent" — Assigns to the car booking sub-Agent.
                - "flights-agent" — Assigns to the flight management sub-Agent.
                - "hotels-agent" — Assigns to the hotel booking sub-Agent.
                - "activity-agent" — Assigns to the activity sub-Agent.

        Returns:
            Assignment confirmation or error message.
        """
        # 1. Validate target Agent -> scope
        if agent_name not in SCOPE_MAP:
            available = ", ".join(SCOPE_MAP.keys())
            return f"Error: Unknown Agent '{agent_name}'. Available: {available}"

        scope = SCOPE_MAP[agent_name]
        source_dir = f"/skills/main/{skill_name}"
        target_dir = f"/skills/{scope}/{skill_name}"

        # 2. Check if the source skill exists
        check = sandbox_backend.execute(f"test -f {source_dir}/SKILL.md")
        if check.exit_code != 0:
            return (
                f"Error: Skill '{skill_name}' does not exist under {source_dir}/.\n"
                f"Please complete skill download/creation and testing first."
            )

        # 3. Copy to the target scope directory (skip copying if it's the main Agent, as it's already in place)
        if agent_name == "main":
            cp_result = "(Main Agent skill is already in place, no need to move)"
        else:
            result = sandbox_backend.execute(
                f"mkdir -p {target_dir} && cp -r {source_dir}/* {target_dir}/"
            )
            if result.exit_code != 0:
                return f"Error: Failed to copy skill files:\n{result.output}"
            verify = sandbox_backend.execute(f"ls {target_dir}/")
            cp_result = (
                f"✅ Copied to sandbox {target_dir}/\n"
                f"Files:\n{verify.output.strip()}"
            )

        # 4. Persist to StoreBackend (read files from /skills/main/ -> store.aput)
        persist_report = await _persist_skill(sandbox_backend, store, skills_namespace, skill_name, scope)

        # 5. Clean up archive packages (*.zip, *.tar.gz, *.tar, *.tgz under /skills/main/)
        cleanup_report = _cleanup_packages(sandbox_backend)

        return (
            f"✅ Skill '{skill_name}' assigned to Agent '{agent_name}' (scope: {scope})\n"
            f"{cp_result}\n"
            f"{persist_report}\n"
            f"{cleanup_report}"
        )

    assign_skill.name = "assign_skill"
    return assign_skill


# ============================================================
# Internal Helper Functions
# ============================================================

async def _persist_skill(sandbox_backend, store, namespace, skill_name: str, scope: str) -> str:
    """Writes skill files to the StoreBackend for persistence.

    Reads all files from the sandbox /skills/main/{skill_name}/ directory
    and writes them to the store namespace under the key: /{scope}/{skill_name}/...

    Returns:
        A description of the persistence result.
    """
    source_dir = f"/skills/main/{skill_name}"
    now = datetime.now(timezone.utc).isoformat()

    # List all files in the source directory
    ls_result = sandbox_backend.execute(f"find {source_dir} -type f")
    if ls_result.exit_code != 0:
        return f"⚠️ Persistence failed: Unable to list files under {source_dir}/"

    file_paths = [p.strip() for p in ls_result.output.strip().split("\n") if p.strip()]
    if not file_paths:
        return "⚠️ Persistence skipped: Source directory is empty"

    persisted_count = 0
    for sandbox_path in file_paths:
        # Calculate relative path -> StoreBackend key
        # e.g., /skills/main/web-fetcher/SKILL.md -> /main/web-fetcher/SKILL.md
        rel = sandbox_path[len(f"/skills/main/"):]
        store_key = f"/{scope}/{rel}"

        # Read file content
        try:
            dl = sandbox_backend.download_files([sandbox_path])
            if not dl or dl[0].error:
                continue
            content_bytes = dl[0].content
            content_str = content_bytes.decode("utf-8") if isinstance(content_bytes, bytes) else str(content_bytes)
        except Exception:
            continue

        # Write to Store (format consistent with StoreBackend)
        try:
            await store.aput(
                namespace,
                store_key,
                {
                    "content": [content_str],
                    "created_at": now,
                    "modified_at": now,
                },
            )
            persisted_count += 1
        except Exception as e:
            return f"⚠️ Persistence partially failed ({store_key}: {e}), {persisted_count} files successfully persisted"

    return f"💾 Persistence complete: {persisted_count} files -> StoreBackend /persisted-skills/{scope}/{skill_name}/"


def _cleanup_packages(sandbox_backend) -> str:
    """Deletes archive package files under /skills/main/.

    Returns:
        A description of the cleanup result.
    """
    patterns = "*.zip *.tar.gz *.tar *.tgz *.tar.bz2 *.tar.xz"
    cmd = f"cd /skills/main/ && rm -f {patterns} 2>/dev/null; ls {patterns} 2>/dev/null || echo 'none'"
    result = sandbox_backend.execute(cmd)

    output = result.output.strip()
    if output == "none" or not output:
        return "🧹 Archive packages cleaned up"
    else:
        return f"🧹 Archive packages cleaned up (residual: {output})"
