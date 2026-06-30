"""
Skill synchronization middleware.

Before each Agent execution cycle, synchronizes skill files under the local
src/skills/ directory with the sandbox. If any changes are detected, a system
notification is inserted into the conversation to inform the Agent that new
skills are available.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from deepagents.backends.sandbox import BaseSandbox  # Uses the generic sandbox backend interface.
from agent.config import LOCAL_SKILLS_DIR, SANDBOX_SKILLS_ROOT


class SkillsSyncMiddleware(AgentMiddleware):
    """Middleware for synchronizing skill files, relying on the sandbox backend's file operations."""

    def __init__(self, backend: BaseSandbox) -> None:
        super().__init__()
        self.backend = backend
        # Cache local file hashes to avoid unnecessary synchronization.
        self._last_hashes: dict[str, str] = {}

    # --------------------- Hooks ---------------------
    def before_agent(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        new_skills = self._sync_files()
        if new_skills:
            return self._make_notification(new_skills)
        return None

    async def abefore_agent(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        import asyncio

        loop = asyncio.get_running_loop()
        new_skills = await loop.run_in_executor(None, self._sync_files)
        if new_skills:
            return self._make_notification(new_skills)
        return None

    # --------------------- File Synchronization ---------------------
    def _sync_files(self) -> list[str]:
        """Scan the local skills directory and upload new or modified files to the sandbox.

        Returns:
            A list of skill names that have been updated.
        """
        local_skills_dir = Path(LOCAL_SKILLS_DIR)
        if not local_skills_dir.exists():
            return []

        updated_skills: list[str] = []

        for skill_dir in local_skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_name = skill_dir.name
            sandbox_skill_dir = f"{SANDBOX_SKILLS_ROOT}/{skill_name}"

            files_to_upload: list[tuple[str, bytes]] = []
            has_changes = False

            for local_file in skill_dir.rglob("*"):
                if not local_file.is_file():
                    continue
                relative_path = local_file.relative_to(skill_dir).as_posix()
                sandbox_path = f"{sandbox_skill_dir}/{relative_path}"

                with open(local_file, "rb") as f:
                    local_content = f.read()
                local_hash = hashlib.md5(local_content).hexdigest()
                cache_key = f"{skill_name}/{relative_path}"

                # Local file hash unchanged; skip.
                if self._last_hashes.get(cache_key) == local_hash:
                    continue

                # Compare with the sandbox file (use test -f first to avoid download_files logging a 404 ERROR).
                check = self.backend.execute(f"test -f {sandbox_path}")
                if check.exit_code == 0:
                    try:
                        results = self.backend.download_files([sandbox_path])
                        if results and results[0].content and not results[0].error:
                            remote_content = results[0].content
                            if isinstance(remote_content, str):
                                remote_content = remote_content.encode("utf-8")
                            remote_hash = hashlib.md5(remote_content).hexdigest()
                            if remote_hash == local_hash:
                                self._last_hashes[cache_key] = local_hash
                                continue
                    except Exception:
                        pass  # Failed to read the remote file; upload is required.

                files_to_upload.append((sandbox_path, local_content))
                self._last_hashes[cache_key] = local_hash
                has_changes = True

            if has_changes:
                self.backend.upload_files(files_to_upload)
                updated_skills.append(skill_name)

        return updated_skills

    # --------------------- Notification Generation ---------------------
    @staticmethod
    def _make_notification(skill_names: list[str]) -> dict[str, Any]:
        skills_list = "\n".join(f"- {name}" for name in skill_names)
        notice = (
            f"[System Notification] The following skill packages have been updated:\n{skills_list}\n"
            "Please use `ls /skills/` to view the details. They may be helpful for the current task."
        )
        return {"messages": [SystemMessage(content=notice)]}