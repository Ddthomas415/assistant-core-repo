from __future__ import annotations

import re

from core.policy import evaluate_tool_request
from core.types import (
    PendingClarification,
    PendingConfirmation,
    PolicyOutcome,
    RequestedAction,
    RouteDecision,
    ToolRequest,
)

INFORMATIONAL_KEYWORDS = {"what", "how", "why", "explain", "help", "can you"}
SEARCH_KEYWORDS   = {"search", "google", "look up", "lookup", "find"}
FETCH_KEYWORDS    = {"fetch", "browse", "open url", "get page"}
READ_KEYWORDS     = {"read", "show", "open"}
LIST_KEYWORDS     = {"list", "workspace", "files"}
WRITE_KEYWORDS    = {"write", "create", "make"}
EDIT_KEYWORDS     = {"edit", "update", "change"}
WEATHER_KEYWORDS  = {"weather", "temperature", "forecast", "how hot", "how cold", "rain"}
CODE_KEYWORDS     = {"run", "execute", "python", "script", "compute"}
SCREENSHOT_KEYWORDS = {"screenshot", "screen capture", "what's on my screen", "capture screen"}

_URL_RE = re.compile(r"https?://\S+")


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _extract_filename(text: str) -> str | None:
    for token in text.replace(",", " ").split():
        if token.endswith(".py"):
            return token
    return None


def _extract_search_query(text: str) -> str | None:
    prefixes = sorted(
        ["search for ", "search ", "google ", "look up ", "lookup ", "find "],
        key=len, reverse=True,
    )
    for prefix in prefixes:
        if text.startswith(prefix):
            q = text[len(prefix):].strip()
            return q if q else None
    return None


def _extract_url(text: str) -> str | None:
    m = _URL_RE.search(text)
    return m.group(0).rstrip(".,)>") if m else None


def route_user_message(
    user_message: str,
    *,
    pending_clarification: PendingClarification | None = None,
    pending_confirmation: PendingConfirmation | None = None,
) -> tuple[RouteDecision, PolicyOutcome | None]:
    text = _normalize(user_message)

    # Pending state
    if pending_clarification is not None:
        return (RouteDecision(kind="clarify", clarification_prompt=pending_clarification.prompt, clarification_target=pending_clarification.target), None)

    if pending_confirmation is not None:
        if text in {"yes", "y", "confirm"}:
            tool_request = ToolRequest(
                tool_name=pending_confirmation.requested_action.action_name,
                arguments=pending_confirmation.requested_action.arguments,
                user_facing_label=pending_confirmation.requested_action.user_facing_label,
            )
            return (RouteDecision(kind="tool", tool_request=tool_request), evaluate_tool_request(tool_request))
        if text in {"no", "n", "cancel"}:
            return (RouteDecision(kind="answer", answer_text="Okay, I canceled that action."), None)
        return (RouteDecision(kind="confirm", confirmation_prompt=pending_confirmation.prompt, requested_action=pending_confirmation.requested_action), None)

    # URL → fetch_page
    url = _extract_url(text)
    if url:
        req = ToolRequest(tool_name="fetch_page", arguments={"url": url}, user_facing_label=f"fetch {url}")
        return (RouteDecision(kind="tool", tool_request=req), evaluate_tool_request(req))

    # Weather (before informational — "what is the weather" matches both)
    if any(kw in text for kw in WEATHER_KEYWORDS):
        location = None
        for kw in ["in ", "for ", "at "]:
            if kw in text:
                parts = text.split(kw, 1)
                if len(parts) > 1 and parts[1].strip():
                    location = parts[1].strip()
                    break
        req = ToolRequest(tool_name="get_weather", arguments={"location": location}, user_facing_label=f"get weather{' for ' + location if location else ''}")
        return (RouteDecision(kind="tool", tool_request=req), evaluate_tool_request(req))

    # Screenshot (before informational)
    if any(kw in text for kw in SCREENSHOT_KEYWORDS):
        question = None
        for kw in ["and ", "then ", "to "]:
            if kw in text:
                question = text.split(kw, 1)[-1].strip()
                break
        req = ToolRequest(tool_name="take_screenshot", arguments={"question": question}, user_facing_label="take screenshot")
        return (RouteDecision(kind="tool", tool_request=req), evaluate_tool_request(req))

    # Code execution
    _code_words = text.split()
    if any((text.startswith(kw + " ") or text == kw) and kw not in {"find"} for kw in CODE_KEYWORDS) or "```" in user_message:
        code = ""
        for marker in ["```python", "```", "`"]:
            if marker in text:
                parts = text.split(marker)
                if len(parts) >= 3:
                    code = parts[1].replace("python", "", 1).strip()
                    break
        action = RequestedAction(action_name="execute_code", arguments={"code": code, "language": "python"}, user_facing_label="execute code")
        return (
            RouteDecision(kind="confirm", confirmation_prompt="Do you want me to execute this code?", requested_action=action),
            PolicyOutcome(kind="require_confirmation", reason="code execution requires approval", blocking_code=None, advisory_notes=[]),
        )

    # Search
    if any(text.startswith(word) for word in SEARCH_KEYWORDS):
        query = _extract_search_query(text)
        if not query:
            return (RouteDecision(kind="clarify", clarification_prompt="What should I search for?", clarification_target="user_intent"),
                    PolicyOutcome(kind="require_clarification", reason="search query missing", blocking_code=None, advisory_notes=[]))
        req = ToolRequest(tool_name="web_search", arguments={"query": query}, user_facing_label=f'searching for "{query}"')
        return (RouteDecision(kind="tool", tool_request=req), evaluate_tool_request(req))

    # Informational
    if any(text.startswith(word) for word in INFORMATIONAL_KEYWORDS):
        return (RouteDecision(kind="answer", answer_text="I can help with file tasks, web search, weather, code execution, and more."), None)

    # List workspace
    if any(text.startswith(word) for word in LIST_KEYWORDS):
        req = ToolRequest(tool_name="list_workspace", arguments={}, user_facing_label="list workspace")
        return (RouteDecision(kind="tool", tool_request=req), evaluate_tool_request(req))

    # Read file
    if any(text.startswith(word) for word in READ_KEYWORDS):
        filename = _extract_filename(text)
        if not filename:
            return (RouteDecision(kind="clarify", clarification_prompt="Which file should I read?", clarification_target="filename"),
                    PolicyOutcome(kind="require_clarification", reason="filename missing", blocking_code=None, advisory_notes=[]))
        req = ToolRequest(tool_name="read_file", arguments={"filename": filename}, user_facing_label=f"read {filename}")
        return (RouteDecision(kind="tool", tool_request=req), evaluate_tool_request(req))

    # Write file
    if any(text.startswith(word) for word in WRITE_KEYWORDS):
        filename = _extract_filename(text)
        if not filename:
            return (RouteDecision(kind="clarify", clarification_prompt="What filename should I use?", clarification_target="filename"),
                    PolicyOutcome(kind="require_clarification", reason="filename missing", blocking_code=None, advisory_notes=[]))
        action = RequestedAction(action_name="write_file", arguments={"filename": filename, "content": ""}, user_facing_label=f"write {filename}")
        return (RouteDecision(kind="confirm", confirmation_prompt=f"Do you want me to write {filename}?", requested_action=action),
                PolicyOutcome(kind="require_confirmation", reason="modifying actions require approval", blocking_code=None, advisory_notes=[]))

    # Edit file
    if any(text.startswith(word) for word in EDIT_KEYWORDS):
        filename = _extract_filename(text)
        if not filename:
            return (RouteDecision(kind="clarify", clarification_prompt="Which file should I edit?", clarification_target="filename"),
                    PolicyOutcome(kind="require_clarification", reason="filename missing", blocking_code=None, advisory_notes=[]))
        action = RequestedAction(action_name="edit_file", arguments={"filename": filename, "content": ""}, user_facing_label=f"edit {filename}")
        return (RouteDecision(kind="confirm", confirmation_prompt=f"Do you want me to edit {filename}?", requested_action=action),
                PolicyOutcome(kind="require_confirmation", reason="modifying actions require approval", blocking_code=None, advisory_notes=[]))

    return (RouteDecision(kind="answer", answer_text="I'm not sure yet. Try asking a file or workspace question, search, or 'take a screenshot'."), None)
