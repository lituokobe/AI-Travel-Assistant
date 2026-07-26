"""Scrub internal preference / workflow vocabulary from user-visible assistant text."""

from __future__ import annotations

import re

# Phrases that must not appear in customer-facing copy (case-insensitive).
_PHRASE_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(?:given|with|for)\s+your\s+"
            r"(?:low|medium|high)\s+price\s+sensitivity,?\s*",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(
            r"\byour\s+(?:low|medium|high)\s+price\s+sensitivity,?\s*",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(r"\bprice\s+sensitivity\b[:\s]*", re.IGNORECASE),
        "",
    ),
    (
        re.compile(
            r"\blet me follow the package planning process\.?",
            re.IGNORECASE,
        ),
        "Let me get started.",
    ),
    (
        re.compile(
            r"\bfollow(?:ing)?\s+the\s+package\s+planning\s+process\.?",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(r"\bpackage\s+planning\s+process\b", re.IGNORECASE),
        "",
    ),
    (
        re.compile(
            r"\bcompound[- ]travel[- ]package\b",
            re.IGNORECASE,
        ),
        "",
    ),
]

# Collapse awkward gaps after removals.
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def sanitize_user_facing_text(text: str) -> str:
    """Return text safe to show in the chat bubble."""
    if not text:
        return text
    out = text
    for pattern, repl in _PHRASE_REPLACEMENTS:
        out = pattern.sub(repl, out)
    out = _MULTI_SPACE.sub(" ", out)
    out = _MULTI_NEWLINE.sub("\n\n", out)
    # Join accidental duplicate sentences when removal left "Let me ...Let me"
    out = re.sub(
        r"(Let me get started\.)\s*\1+",
        r"\1",
        out,
        flags=re.IGNORECASE,
    )
    return out.strip()
