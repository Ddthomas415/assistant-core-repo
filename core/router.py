from __future__ import annotations

from core.policy import evaluate_tool_request
from core.types import (
    PendingClarification,
    PendingConfirmation,
    PolicyOutcome,
    RequestedAction,
    RouteDecision,
    ToolRequest,
)

INFORMATIONAL_KEYWORDS = {
    "what",
    "how",
    "why",
    "explain",
    "help",
    "can you",
}

READ_KEYWORDS = {"read", "show", "open"}
LIST_KEYWORDS = {"list", "workspace", "files"}
WRITE_KEYWORDS = {"write", "create", "make"}
EDIT_KEYWORDS = {"edit", "update", "change"}


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _extract_filename(text: str) -> str | None:
    for token in text.replace(",", " ").split():
        if token.endswith(".py"):
            return token
    return None


def route_user_message(
    user_message: str,
    *,
    pending_clarification: PendingClarification | None = None,
    pending_confirmation: PendingConfirmation | None = None,
) -> tuple[RouteDecision, PolicyOutcome | None]:
    """
    Route a user message into one of four kinds:
    - answer
    - clarify
    - confirm
    - tool
    """
    text = _normalize(user_message)

    if pending_clarification is not None:
        return (
            RouteDecision(
                kind="clarify",
                clarification_prompt=pending_clarification.prompt,
                clarification_target=pending_clarification.target,
            ),
            None,
        )

    if pending_confirmation is not None:
        if text in {"yes", "y", "confirm"}:
            tool_request = ToolRequest(
                tool_name=pending_confirmation.requested_action.action_name,
                arguments=pending_confirmation.requested_action.arguments,
                user_facing_label=pending_confirmation.requested_action.user_facing_label,
            )
            return (
                RouteDecision(kind="tool", tool_request=tool_request),
                evaluate_tool_request(tool_request),
            )

        if text in {"no", "n", "cancel"}:
            return (
                RouteDecision(
                    kind="answer",
                    answer_text="Okay, I canceled that action.",
                ),
                None,
            )

        return (
            RouteDecision(
                kind="confirm",
                confirmation_prompt=pending_confirmation.prompt,
                requested_action=pending_confirmation.requested_action,
            ),
            None,
        )

    if any(text.startswith(word) for word in INFORMATIONAL_KEYWORDS):
        return (
            RouteDecision(
                kind="answer",
                answer_text="I can help with file and workspace tasks, or answer simple questions.",
            ),
            None,
        )

    if any(text.startswith(word) for word in LIST_KEYWORDS):
        tool_request = ToolRequest(
            tool_name="list_workspace",
            arguments={},
            user_facing_label="list workspace",
        )
        return (
            RouteDecision(kind="tool", tool_request=tool_request),
            evaluate_tool_request(tool_request),
        )

    if any(text.startswith(word) for word in READ_KEYWORDS):
        filename = _extract_filename(text)
        if not filename:
            return (
                RouteDecision(
                    kind="clarify",
                    clarification_prompt="Which file should I read?",
                    clarification_target="filename",
                ),
                PolicyOutcome(
                    kind="require_clarification",
                    reason="filename missing",
                    blocking_code=None,
                    advisory_notes=["Need filename before proceeding."],
                ),
            )

        tool_request = ToolRequest(
            tool_name="read_file",
            arguments={"filename": filename},
            user_facing_label=f"read {filename}",
        )
        return (
            RouteDecision(kind="tool", tool_request=tool_request),
            evaluate_tool_request(tool_request),
        )

    if any(text.startswith(word) for word in WRITE_KEYWORDS):
        filename = _extract_filename(text)
        if not filename:
            return (
                RouteDecision(
                    kind="clarify",
                    clarification_prompt="What filename should I use?",
                    clarification_target="filename",
                ),
                PolicyOutcome(
                    kind="require_clarification",
                    reason="filename missing",
                    blocking_code=None,
                    advisory_notes=["Need filename before proceeding."],
                ),
            )

        action = RequestedAction(
            action_name="write_file",
            arguments={"filename": filename, "content": ""},
            user_facing_label=f"write {filename}",
        )
        return (
            RouteDecision(
                kind="confirm",
                confirmation_prompt=f"Do you want me to write {filename}?",
                requested_action=action,
            ),
            PolicyOutcome(
                kind="require_confirmation",
                reason="modifying actions require approval",
                blocking_code=None,
                advisory_notes=["Await explicit user confirmation before execution."],
            ),
        )

    if any(text.startswith(word) for word in EDIT_KEYWORDS):
        filename = _extract_filename(text)
        if not filename:
            return (
                RouteDecision(
                    kind="clarify",
                    clarification_prompt="Which file should I edit?",
                    clarification_target="filename",
                ),
                PolicyOutcome(
                    kind="require_clarification",
                    reason="filename missing",
                    blocking_code=None,
                    advisory_notes=["Need filename before proceeding."],
                ),
            )

        action = RequestedAction(
            action_name="edit_file",
            arguments={"filename": filename, "content": ""},
            user_facing_label=f"edit {filename}",
        )
        return (
            RouteDecision(
                kind="confirm",
                confirmation_prompt=f"Do you want me to edit {filename}?",
                requested_action=action,
            ),
            PolicyOutcome(
                kind="require_confirmation",
                reason="modifying actions require approval",
                blocking_code=None,
                advisory_notes=["Await explicit user confirmation before execution."],
            ),
        )

    return (
        RouteDecision(
            kind="answer",
            answer_text="I’m not sure yet. Try asking a file or workspace question.",
        ),
        None,
    )
