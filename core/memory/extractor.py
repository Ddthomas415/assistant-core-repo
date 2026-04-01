"""
Memory extractor.

Sends the last N conversation turns to the LLM and asks it to extract
discrete, storable facts about the user. Runs after each turn, only
when ANTHROPIC_API_KEY is set.

Facts are things like:
  - "User's name is Alex"
  - "User is building a Python AI assistant"
  - "User prefers dark mode"
  - "User's workspace uses pyproject.toml"

Non-facts (greetings, tool outputs, questions) are ignored.
"""
from __future__ import annotations

import json
import os
from typing import Any

_API_URL         = "https://api.anthropic.com/v1/messages"
_MODEL           = os.getenv("ASSISTANT_MODEL", "claude-haiku-4-5-20251001")
_EXTRACT_WINDOW  = 6   # last N messages to inspect
_MAX_FACTS       = 5   # max facts extracted per turn

_SYSTEM = """\
You are a memory extraction assistant. Given a short conversation excerpt, \
extract discrete facts about the user that are worth remembering long-term.

Rules:
- Only extract facts about the USER (their name, preferences, projects, decisions, context).
- Do not extract facts about the assistant's actions or tool outputs.
- Each fact must be a single self-contained sentence.
- Omit trivial or already-obvious facts.
- If there are no new facts worth storing, return an empty list.
- Respond with ONLY a JSON array of strings, no other text.\
"""


def extract_facts(
    messages: list[dict[str, Any]],
    *,
    source_session_id: str | None = None,
) -> list[str]:
    """
    Extract storable facts from a list of conversation messages.

    Returns a list of fact strings (may be empty).
    Silently returns [] when ANTHROPIC_API_KEY is not set or on any error.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return []

    window = _build_window(messages)
    if not window:
        return []

    try:
        return _call_extractor(window, api_key=api_key)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_window(messages: list[dict[str, Any]]) -> str:
    """Format the last N messages into a plain text excerpt."""
    recent = messages[-_EXTRACT_WINDOW:]
    lines: list[str] = []
    for msg in recent:
        role    = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            # Truncate long assistant messages (tool outputs, etc.)
            short = content[:300] + ("…" if len(content) > 300 else "")
            lines.append(f"Assistant: {short}")
    return "\n".join(lines)


def _call_extractor(excerpt: str, *, api_key: str) -> list[str]:
    import requests  # noqa: PLC0415

    response = requests.post(
        _API_URL,
        headers={
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json={
            "model":      _MODEL,
            "max_tokens": 512,
            "system":     _SYSTEM,
            "messages":   [
                {
                    "role":    "user",
                    "content": (
                        f"Extract memorable facts from this conversation:\n\n{excerpt}"
                    ),
                }
            ],
        },
        timeout=15,
    )
    response.raise_for_status()

    data        = response.json()
    text_blocks = [b for b in data.get("content", []) if b.get("type") == "text"]
    raw         = "\n".join(b.get("text", "") for b in text_blocks).strip()

    if not raw:
        return []

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    facts: list[str] = json.loads(raw)

    if not isinstance(facts, list):
        return []

    return [str(f).strip() for f in facts if str(f).strip()][:_MAX_FACTS]
