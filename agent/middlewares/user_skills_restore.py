"""
User skills restoration middleware.

Before each Agent execution cycle, restores skills persisted in the StoreBackend
to the sandbox under /skills/{scope}/{skill_name}/ so that sub-agents can
discover and use them through progressive disclosure.

Responsibilities compared with SkillsSyncMiddleware:

- SkillsSyncMiddleware: Local src/skills/ → Sandbox (built-in skills)
- UserSkillsRestoreMiddleware: StoreBackend → Sandbox (persisted user skills)
"""

from __future__ import annotations

from typing import Any
from langchain.agents.middleware import AgentMiddleware


class UserSkillsRestoreMiddleware(AgentMiddleware):
    """Middleware for restoring persisted skills from the StoreBackend to the sandbox."""

    def __init__(self, backend, skills_namespace) -> None:
        """
        Args:
            backend: An OpenSandboxBackend instance responsible for uploading files.
            skills_namespace: The namespace tuple used for skills in the StoreBackend.
        """
        super().__init__()
        self.backend = backend
        self.namespace = skills_namespace

    async def abefore_agent(
        self, state: dict[str, Any], runtime: Any
    ) -> dict[str, Any] | None:
        """Before execution: read persisted skills from the StoreBackend and upload them to the sandbox."""
        store = runtime.store
        files = await self._collect_skills(store)
        if files:
            await self.backend.aupload_files(files)
        return None

    def before_agent(
        self, state: dict[str, Any], runtime: Any
    ) -> dict[str, Any] | None:
        """Synchronous version: no operation (skill restoration is supported only in the asynchronous version)."""
        return None

    # --------------------- Internal Methods ---------------------
    async def _collect_skills(self, store) -> list[tuple[str, bytes]]:
        """
        Collect all persisted skill files from the StoreBackend.

        StoreBackend key format: /{scope}/{skill_name}/...
        Sandbox destination path: /skills/{scope}/{skill_name}/...

        Returns:
            A list of (sandbox_path, file_content_bytes) tuples.
        """
        files: list[tuple[str, bytes]] = []

        try:
            items = await store.asearch(self.namespace)
        except Exception:
            return files

        for item in items:
            key = str(item.key).lstrip("/")

            # Key format: {scope}/{skill_name}/...
            # Mapped to: /skills/{scope}/{skill_name}/...
            parts = key.split("/", 1)
            if len(parts) != 2:
                continue
            scope, rest = parts
            sandbox_path = f"/skills/{scope}/{rest}"

            content = item.value
            if isinstance(content, dict):
                content = content.get("content", "")
            if isinstance(content, str):
                content = content.encode("utf-8")
            if not content:
                continue

            files.append((sandbox_path, content))

        return files