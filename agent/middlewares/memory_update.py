"""
Automatic memory update middleware.

After each Agent reply (aafter_agent hook), automatically extracts
destination names and query summaries from the conversation and updates
the user preferences file in StoreBackend.

The Agent does not need to manually maintain recent_destinations / recent_queries — the system handles it.

Usage:
    from agent.middlewares.memory_update import MemoryUpdateMiddleware
    middleware = MemoryUpdateMiddleware(model=SUMMARY_MODEL)
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from agent.logger import logger

# Travel-related keywords that trigger automatic memory updates
_TRIGGER_KEYWORDS = [
    "hotel", "car booking", "flight", "tour", "travel",
    "订票", "门票", "景点", "sight-seeing", "trip", "exhibition",
    "订酒店", "观光", "游览", "户外", "演出", "游玩", "头等舱", "商务舱",
    "经济舱", "出差", "订车", "快捷酒店", "五星级酒店",
]

# Meaningless message patterns to skip for updates
_SKIP_PATTERNS = [
    "你好", "在吗", "嗨", "hello", "hi", "hey",
    "你能做什么", "你有哪些功能", "你是谁",
    "我之前的偏好", "我的偏好", "我的记忆",
]


def _is_meaningful_travel_comm(messages: list[BaseMessage]) -> str|None:
    """Check whether the last user message is a meaningful travel-related interaction.

    Returns:
        User message text when meaningful, or None when the update should be skipped.
    """
    # Find the last user message, scanning from the end
    last_user_msg = None
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None)
        if msg_type == "human":
            last_user_msg = msg
            break

    if last_user_msg is None:
        return None

    content = last_user_msg.content
    if isinstance(content, list):
        content = " ".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    content = str(content).strip()

    if not content:
        return None

    # Skip meaningless messages
    content_lower = content.lower().replace(" ", "")
    for pattern in _SKIP_PATTERNS:
        if pattern.lower().replace(" ", "") in content_lower:
            return None

    # Check for travel arrangement keywords
    has_travel_keyword = any(
        kw.lower() in content_lower for kw in _TRIGGER_KEYWORDS
    )
    if not has_travel_keyword:
        # Fallback: check whether a sub-agent was delegated (task tool call in messages)
        has_subagent_call = False
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.get("name") == "task":
                        has_subagent_call = True
                        break
            if has_subagent_call:
                break
        if not has_subagent_call:
            return None

    return content


def _extract_ai_summary(messages: list[BaseMessage]) -> str:
    """Extract the first 300 characters of the last AI message as a summary."""
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "ai":
            content = msg.content
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            return str(content)[:300]
    return ""


async def _extract_entities(
    model: BaseChatModel, user_message: str, ai_summary: str
) -> dict[str, Any]:
    """Use an LLM to extract destinations and a query summary from the conversation.

    Returns:
        {"destinations": [...], "query": "..."} or {"destinations": [], "query": ""}
    """
    prompt = f"""Extract travel-related entities from this conversation.

Rules:
1. "destinations": Recent destinations/places the user have visited. Empty list if none.
2. "query": One-line summary of the user's travel need. Empty string if not travel-related.

User message: {user_message}

Assistant response summary: {ai_summary}

Return ONLY a JSON object, no other text:
{{"destinations": ["PlaceA", "PlaceB"], "query": "brief summary"}}"""

    try:
        response = await model.ainvoke(prompt)

        # Extract JSON from the reply
        text = response.content
        if isinstance(text, list):
            text = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in text
            )
        text = str(text).strip()

        # Extract JSON block
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            result = json.loads(text[start:end + 1])
            return {
                "destinations": result.get("destinations", []),
                "query": result.get("query", ""),
            }
    except Exception as e:
        logger.warning(f"MemoryUpdateMiddleware: LLM extraction failed, skipping this update \n {e}", exc_info=True)

    return {"destinations": [], "query": ""}


def _create_file_value(content_str: str) -> dict:
    """Create a StoreBackend-compatible file value (consistent with deepagents.backends.utils.create_file_data)."""
    lines = content_str.split("\n")
    now = datetime.now(timezone.utc).isoformat()
    return {
        "content": lines,
        "created_at": now,
        "modified_at": now,
    }


class MemoryUpdateMiddleware(AgentMiddleware):
    """Automatically update recent_destinations / recent_queries in the user memory file after Agent replies.

    Does not rely on the Agent to remember — the middleware extracts, merges, and writes back automatically.
    """

    def __init__(self, model: BaseChatModel) -> None:
        super().__init__()
        self.model = model

    # ---- Sync hook (no-op) ----
    def after_agent(
        self, state: dict[str, Any], runtime: Any
    ) -> dict[str, Any]|None:
        return None

    # ---- Async hook (core logic) ----
    async def aafter_agent(
        self, state: dict[str, Any], runtime: Any
    ) -> dict[str, Any]|None:
        """Triggered after Agent reply completes: extract entities and update memory."""
        try:
            # 1. Get user_id
            ctx = getattr(runtime, "context", None)
            if ctx is None:
                return None
            user_id = getattr(ctx, "user_id", None)
            if not user_id:
                return None

            # 2. Get message list
            messages: list[BaseMessage] = state.get("messages", [])
            if not messages:
                return None

            # 3. Decide whether an update is needed
            user_message = _is_meaningful_travel_comm(messages)
            if user_message is None:
                return None

            # 4. Extract AI summary
            ai_summary = _extract_ai_summary(messages)

            # 5. LLM entity extraction for recent destinations
            extracted = await _extract_entities(self.model, user_message, ai_summary)
            destinations = extracted.get("destinations", [])
            query = extracted.get("query", "")

            if not destinations and not query:
                return None

            logger.info(
                f"MemoryUpdateMiddleware: user={user_id}, "
                f"destinations={destinations}, query={query[:50]}"
            )

            # 6. Read current preferences file from store
            store = getattr(runtime, "store", None)
            if store is None:
                logger.warning("MemoryUpdateMiddleware: runtime.store is unavailable")
                return None

            namespace = (user_id,)
            key = f"/{user_id}/preferences.md"

            try:
                item = await store.aget(namespace, key)
            except Exception as e:
                item = None
                logger.warning(f"Cannot get name space from Store: {e}")

            # 7. Parse existing content or create defaults
            current_lines: list[str] = []
            if item is not None and hasattr(item, "value"):
                value = item.value
                if isinstance(value, dict):
                    content = value.get("content", [])
                    if isinstance(content, list):
                        current_lines = [str(line) for line in content]
                    elif isinstance(content, str):
                        current_lines = content.split("\n")
                elif isinstance(value, str):
                    current_lines = value.split("\n")

            updated_content = _merge_preferences(
                current_lines, destinations, query
            )

            # 8. Write back to store
            file_value = _create_file_value(updated_content)
            await store.aput(namespace, key, file_value)

            logger.info(
                f"MemoryUpdateMiddleware: updated memory for {user_id} "
                f"(destinations={len(destinations)}, query={'yes' if query else 'no'})"
            )

        except Exception as e:
            logger.warning(f"MemoryUpdateMiddleware: update failed \n {e}", exc_info=True)

        return None


def _merge_preferences(
    current_lines: list[str], new_destinations: list[str], new_query: str
) -> str:
    """Merge new destinations/query into existing preference content.

    Strategy: remove old recent_destinations / recent_queries blocks, then append merged versions at the end.
    """
    # 1. Parse existing destinations and queries
    existing_destinations: list[str] = []
    existing_queries: list[str] = []

    def _parse_list_items(lines: list[str], start_idx: int) -> tuple:
        """Parse list items from start_idx line (recent_xxx: header line)."""
        items: list[str] = []
        title_line = lines[start_idx].strip()

        # Check inline format: recent_destinations: [a, b]
        colon_pos = title_line.find(":")
        if colon_pos != -1:
            inline = title_line[colon_pos + 1:].strip()
            if inline.startswith("[") and inline.endswith("]"):
                inner = inline[1:-1].strip()
                if inner:
                    return [s.strip().strip("'").strip('"') for s in inner.split(",") if s.strip()], 1

        # Multi-line format: collect - xxx items from the next line onward
        count = 1
        for j in range(start_idx + 1, len(lines)):
            stripped = lines[j].strip()
            if stripped.startswith("- "):
                items.append(stripped[2:].strip().strip("'").strip('"'))
                count += 1
            elif stripped and not lines[j].startswith(" "):
                break  # Hit the next top-level field
            else:
                count += 1  # Blank line or comment still belongs to current block
        return items, count

    # 2. Find positions and values of old blocks
    destinations_start = -1
    destinations_len = 0
    queries_start = -1
    queries_len = 0

    for i, line in enumerate(current_lines):
        stripped = line.strip()
        if stripped.startswith("recent_destinations:"):
            destinations_start = i
            existing_destinations, destinations_len = _parse_list_items(current_lines, i)
        elif stripped.startswith("recent_queries:"):
            queries_start = i
            existing_queries, queries_len = _parse_list_items(current_lines, i)

    # 3. Remove old blocks from original content (delete from end to avoid index shift)
    clean_lines = list(current_lines)
    # Sort by start position descending; delete from back to front
    removals = []
    if destinations_start >= 0:
        removals.append((destinations_start, destinations_len))
    if queries_start >= 0:
        removals.append((queries_start, queries_len))
    removals.sort(key=lambda x: x[0], reverse=True)

    for start, length in removals:
        del clean_lines[start:start + length]

    # 4. Merge new and old values
    merged_destinations = list(new_destinations)
    for s in existing_destinations:
        if s not in merged_destinations:
            merged_destinations.append(s)
    merged_destinations = merged_destinations[:10]

    merged_queries = [new_query] if new_query else []
    for q in existing_queries:
        if q.strip() not in [m.strip() for m in merged_queries]:
            merged_queries.append(q)
    merged_queries = merged_queries[:5]

    # 5. Append merged blocks
    result_lines = list(clean_lines)

    # Ensure a blank line separator at the end
    if result_lines and result_lines[-1].strip():
        result_lines.append("")

    result_lines.append("recent_destinations:")
    if merged_destinations:
        for s in merged_destinations:
            result_lines.append(f"  - {s}")
    else:
        result_lines[-1] = "recent_destinations: []"

    result_lines.append("recent_queries:")
    if merged_queries:
        for q in merged_queries:
            result_lines.append(f"  - {q}")
    else:
        result_lines[-1] = "recent_queries: []"

    return "\n".join(result_lines).strip() + "\n"
