"""
Memory retriever.

Searches the fact store for facts relevant to the current user message
and formats them for injection into the planner's system prompt.

No LLM dependency — fast path, always runs.
"""
from __future__ import annotations

from core.memory.store import search

_INJECT_LIMIT = 6   # max facts injected per turn
_MIN_CONTENT  = 10  # ignore facts shorter than this


def retrieve_for_prompt(query: str) -> str | None:
    """
    Return a formatted memory block ready to append to the system prompt.

    Returns None when no relevant facts are found so the caller can
    skip the injection entirely.
    """
    facts = search(query, limit=_INJECT_LIMIT)
    facts = [f for f in facts if len(f.content) >= _MIN_CONTENT]

    if not facts:
        return None

    lines = ["Relevant facts from long-term memory:"]
    for fact in facts:
        lines.append(f"  - {fact.content}")

    return "\n".join(lines)


def retrieve_raw(query: str, *, limit: int = _INJECT_LIMIT) -> list[str]:
    """
    Return a plain list of fact content strings.

    Useful for testing or building custom injections.
    """
    facts = search(query, limit=limit)
    return [f.content for f in facts if len(f.content) >= _MIN_CONTENT]
