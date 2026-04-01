from __future__ import annotations

from core.types import PolicyOutcome, RequestedAction, ToolRequest

ACTION_POLICY = {
    "read_file": "auto",
    "list_workspace": "auto",
    "write_file": "confirm",
    "edit_file": "confirm",
}

REGISTERED_TOOLS = {
    "read_file",
    "write_file",
    "edit_file",
    "list_workspace",
}


def evaluate_tool_request(tool_request: ToolRequest) -> PolicyOutcome:
    """Evaluate whether a tool request is allowed, blocked, or needs confirmation."""
    if tool_request.tool_name not in REGISTERED_TOOLS:
        return PolicyOutcome(
            kind="block",
            reason=f"Unknown tool: {tool_request.tool_name}",
            blocking_code="UNKNOWN_TOOL",
            advisory_notes=["Tool must be registered before execution."],
        )

    mode = ACTION_POLICY.get(tool_request.tool_name)
    if mode == "auto":
        return PolicyOutcome(
            kind="allow",
            reason="safe informational action",
            blocking_code=None,
            advisory_notes=[],
        )

    if mode == "confirm":
        return PolicyOutcome(
            kind="require_confirmation",
            reason="modifying actions require approval",
            blocking_code=None,
            advisory_notes=["Await explicit user confirmation before execution."],
        )

    return PolicyOutcome(
        kind="block",
        reason=f"No policy defined for tool: {tool_request.tool_name}",
        blocking_code="MISSING_POLICY",
        advisory_notes=["Add an explicit policy before execution."],
    )


def evaluate_requested_action(action: RequestedAction) -> PolicyOutcome:
    """Evaluate a requested action using the same policy rules as tool requests."""
    return evaluate_tool_request(
        ToolRequest(
            tool_name=action.action_name,
            arguments=action.arguments,
            user_facing_label=action.user_facing_label,
        )
    )
