"""Ensure per-user preference seeds exist in the long-term memory store.

On startup the agent reads ``/memories/{user_id}/preferences.md`` and, when
that file is *missing*, falls back to writing the global default template from
``agent/memory/AGENTS.md`` (Singapore / Singapore / en / SGD).

Some demo users need a *custom* initial seed instead of the global default
(e.g. Luis is based in Paris, Chinese nationality, EUR currency). This module
idempotently ensures those custom seeds are present in the LangGraph Store
(MongoDB) so a fresh / wiped volume never falls back to the wrong defaults.

Semantics
---------
Only seed when the user's preferences item is **missing**. If it already exists
(possibly evolved by the agent or ``MemoryUpdateMiddleware``), it is left
untouched — long-term memory is preserved across restarts.

Run manually::

    python -m api_view.preference_seed
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from agent.config import STORE, sanitize_store_user_id

logger = logging.getLogger(__name__)

# user_id -> preferences.md YAML content.
#
# The customised fields (base_city / passport_nationality / preferred_language /
# preferred_currency) override the global default template in
# ``agent/memory/AGENTS.md``; the remaining fields reuse the default values so
# users still inherit price_sensitivity / communication_style / etc.
PREFERENCE_SEEDS: dict[str, str] = {
    "3442 587242": (
        "base_city: Paris\n"
        "passport_nationality: China\n"
        "preferred_language: en\n"
        "preferred_currency: EUR\n"
        "airline_memberships: []\n"
        "hotel_memberships: []\n"
        "preferred_travel_types: []\n"
        "price_sensitivity: medium\n"
        "special_preferences: []\n"
        "communication_style: regular\n"
        "recent_destinations: []\n"
        "recent_queries: []\n"
    ),
}


def _file_value(content_str: str) -> dict:
    """Build a Store value dict matching ``memory_update._create_file_value``.

    The deepagents ``StoreBackend`` read path and ``MemoryUpdateMiddleware``
    both accept ``content`` as ``list[str]`` (legacy) or ``str``; we use the
    list form with ``created_at`` / ``modified_at`` to stay byte-for-byte
    consistent with what the middleware itself writes.
    """
    now = datetime.now(timezone.utc).isoformat()
    return {"content": content_str.split("\n"), "created_at": now, "modified_at": now}


async def ensure_preference_seeds() -> int:
    """Ensure each seeded user's ``preferences.md`` exists; seed when missing.

    Returns the number of users that were (re-)seeded.
    """
    seeded = 0
    for user_id, yaml_content in PREFERENCE_SEEDS.items():
        namespace = (sanitize_store_user_id(user_id),)
        key = f"/{namespace[0]}/preferences.md"
        try:
            existing = await STORE.aget(namespace, key)
        except Exception as exc:  # noqa: BLE001  # keep startup resilient
            logger.warning("Preference seed: cannot read %s (%s); skipping", key, exc)
            continue
        if existing is not None:
            logger.info("Preference seed: %s already present; leaving untouched", key)
            continue
        await STORE.aput(namespace, key, _file_value(yaml_content))
        logger.info("Preference seed: wrote custom seed for %s -> %s", user_id, key)
        seeded += 1
    return seeded


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = asyncio.run(ensure_preference_seeds())
    print(f"Seeded {count} user preference file(s).")
