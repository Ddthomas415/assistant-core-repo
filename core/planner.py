"""
LLM-backed planner.

Uses the Anthropic Messages API to route user messages into the same
RouteDecision / PolicyOutcome shape that the heuristic router produces.
Falls back to the heuristic router automatically when:
  - ANTHROPIC_API_KEY is not set
  - PLANNER_MODE=heuristic is set explicitly
  - The API call fails for any reason
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests as _requests

from core.policy import ACTION_POLICY, evaluate_tool_request
from core.router import route_user_message as _heuristic
from core.types import (
    PendingClarification,
    PendingConfirmation,
    PlannerMode,
    PolicyOutcome,
    RequestedAction,
    RouteDecision,
    ToolRequest,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_API_URL = "https://api.anthropic.com/v1/messages"
_MODEL   = os.getenv("ASSISTANT_MODEL", "claude-haiku-4-5-20251001")
_HISTORY_WINDOW = 20   # last N messages sent to the model

_SYSTEM_PROMPT = """\
You are a private AI assistant. You help the user with files, workspace tasks, \
and web research.

Available tools:
  read_file, list_workspace  — run automatically, no user approval needed
  web_search, fetch_page     — run automatically, no user approval needed
  write_file, edit_file      — modifying actions; user must confirm before execution

Workspace: files live in a workspace/ directory.

Rules:
- Use a tool whenever the user's request maps clearly to one.
- For write/edit tools the system will ask the user to confirm; you do not need \
  to ask yourself — just call the tool.
- Answer directly when no tool is appropriate.
- Be concise and transparent about what you are doing.\
"""

# ---------------------------------------------------------------------------
# Tool schema (Anthropic Messages API format)
# ---------------------------------------------------------------------------

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read the contents of a file in the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "File to read."},
            },
            "required": ["filename"],
        },
    },
    {
        "name": "list_workspace",
        "description": "List all files currently in the workspace.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "write_file",
        "description": "Write content to a file in the workspace. Requires user confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "content":  {"type": "string", "description": "Full file content to write."},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Overwrite an existing file in the workspace. Requires user confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "content":  {"type": "string", "description": "New full file content."},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web using DuckDuckGo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_page",
        "description": "Fetch and extract text content from a web page URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url":           {"type": "string"},
                "include_links": {"type": "boolean", "default": False},
            },
            "required": ["url"],
        },
    },
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def plan_turn(
    user_message: str,
    *,
    conversation_history: list[dict[str, Any]] | None = None,
    pending_clarification: PendingClarification | None = None,
    pending_confirmation: PendingConfirmation | None = None,
) -> tuple[RouteDecision, PolicyOutcome | None, PlannerMode]:
    """
    Plan one assistant turn.

    Returns:
        (route_decision, policy_outcome, planner_mode_actually_used)

    planner_mode is one of:
        "model"          — LLM plan succeeded
        "heuristic"      — heuristic used intentionally (pending state or explicit config)
        "model_fallback" — LLM call failed; heuristic used as fallback
    """
    # Pending state always routes through heuristic — the logic there is
    # already correct and tested for yes/no/cancel handling.
    if pending_clarification is not None or pending_confirmation is not None:
        route, policy = _heuristic(
            user_message,
            pending_clarification=pending_clarification,
            pending_confirmation=pending_confirmation,
        )
        return route, policy, "heuristic"

    # Respect explicit override.
    if os.getenv("PLANNER_MODE", "").lower() == "heuristic":
        route, policy = _heuristic(user_message)
        return route, policy, "heuristic"

    # No API key → heuristic silently.
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        route, policy = _heuristic(user_message)
        return route, policy, "heuristic"

    # Try model-backed planning.
    try:
        route, policy = _model_plan(
            user_message,
            history=conversation_history or [],
            api_key=api_key,
        )
        return route, policy, "model"
    except Exception:
        route, policy = _heuristic(user_message)
        return route, policy, "model_fallback"


# ---------------------------------------------------------------------------
# LLM planning
# ---------------------------------------------------------------------------


def _model_plan(
    user_message: str,
    *,
    history: list[dict[str, Any]],
    api_key: str,
) -> tuple[RouteDecision, PolicyOutcome | None]:
    messages = _build_messages(history, user_message)
    system   = _build_system_prompt(user_message)

    response = _requests.post(
        _API_URL,
        headers={
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json={
            "model":      _MODEL,
            "max_tokens": 1024,
            "system":     system,
            "tools":      _TOOLS,
            "messages":   messages,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return _parse_response(data)


def _build_system_prompt(user_message: str) -> str:
    """Build the system prompt, appending relevant long-term memories if any."""
    try:
        from core.memory.retriever import retrieve_for_prompt  # noqa: PLC0415
        memory_block = retrieve_for_prompt(user_message)
    except Exception:
        memory_block = None

    if memory_block:
        return f"{_SYSTEM_PROMPT}\n\n{memory_block}"
    return _SYSTEM_PROMPT


def _build_messages(
    history: list[dict[str, Any]],
    user_message: str,
) -> list[dict[str, Any]]:
    """
    Build the messages array for the Anthropic API.

    - Takes the last _HISTORY_WINDOW messages from session history.
    - Ensures the sequence starts with a user message (API requirement).
    - Appends the current user message at the end.
    """
    window = history[-_HISTORY_WINDOW:]

    # Ensure sequence starts with user role.
    while window and window[0].get("role") != "user":
        window = window[1:]

    # Keep only role and content — strip any extra keys from session format.
    clean: list[dict[str, Any]] = [
        {"role": m["role"], "content": m["content"]}
        for m in window
        if m.get("role") in {"user", "assistant"} and m.get("content")
    ]

    clean.append({"role": "user", "content": user_message})
    return clean


def _parse_response(
    data: dict[str, Any],
) -> tuple[RouteDecision, PolicyOutcome | None]:
    """Convert an Anthropic API response into a RouteDecision."""
    content_blocks: list[dict[str, Any]] = data.get("content", [])

    tool_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]
    text_blocks  = [b for b in content_blocks if b.get("type") == "text"]

    if tool_blocks:
        return _route_tool(tool_blocks[0])

    if text_blocks:
        text = "\n".join(b.get("text", "") for b in text_blocks).strip()
        return (
            RouteDecision(kind="answer", answer_text=text or "I'm not sure how to help with that."),
            None,
        )

    return (
        RouteDecision(kind="answer", answer_text="I'm not sure how to help with that."),
        None,
    )


def _route_tool(
    tool_block: dict[str, Any],
) -> tuple[RouteDecision, PolicyOutcome | None]:
    """Turn a tool_use block into a RouteDecision."""
    tool_name: str          = tool_block["name"]
    tool_input: dict        = tool_block.get("input", {})
    label: str              = _make_label(tool_name, tool_input)
    policy_mode: str | None = ACTION_POLICY.get(tool_name)

    if policy_mode == "confirm":
        action = RequestedAction(
            action_name=tool_name,
            arguments=tool_input,
            user_facing_label=label,
        )
        return (
            RouteDecision(
                kind="confirm",
                confirmation_prompt=f"Do you want me to {label}?",
                requested_action=action,
            ),
            PolicyOutcome(
                kind="require_confirmation",
                reason="modifying actions require approval",
                blocking_code=None,
                advisory_notes=["Await explicit user confirmation before execution."],
            ),
        )

    if policy_mode == "auto":
        tool_request = ToolRequest(
            tool_name=tool_name,
            arguments=tool_input,
            user_facing_label=label,
        )
        return (
            RouteDecision(kind="tool", tool_request=tool_request),
            evaluate_tool_request(tool_request),
        )

    # Unknown or blocked tool — fall through to a safe answer.
    return (
        RouteDecision(kind="answer", answer_text=f"I don't have access to the tool \"{tool_name}\"."),
        None,
    )


def _make_label(tool_name: str, args: dict[str, Any]) -> str:
    """Build a short human-readable label for a tool call."""
    if tool_name == "read_file":      return f"read {args.get('filename', '')}"
    if tool_name == "write_file":     return f"write {args.get('filename', '')}"
    if tool_name == "edit_file":      return f"edit {args.get('filename', '')}"
    if tool_name == "list_workspace": return "list workspace"
    if tool_name == "web_search":     return f"search for \"{args.get('query', '')}\""
    if tool_name == "fetch_page":     return f"fetch {args.get('url', '')}"
    return tool_name
