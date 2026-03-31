from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from core.types import ToolRequest, ToolResult


def _utc_now() -> str:
    """Return a UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def execute_tool_request(tool_request: ToolRequest) -> ToolResult:
    """
    Execute a tool request using the current assistant-core tool surface.

    Supported tools:
    - read_file
    - list_workspace

    Write/edit remain policy-gated for now and are intentionally not executed here yet.
    """
    started_at = _utc_now()

    if tool_request.tool_name == "read_file":
        filename = tool_request.arguments["filename"]
        summary = f"Would read {filename}"
        result = ToolResult(
            ok=True,
            tool_name="read_file",
            execution_id=str(uuid4()),
            summary=summary,
            data={"filename": filename},
            error_code=None,
            error_message=None,
            started_at=started_at,
            finished_at=_utc_now(),
        )
        return result

    if tool_request.tool_name == "list_workspace":
        result = ToolResult(
            ok=True,
            tool_name="list_workspace",
            execution_id=str(uuid4()),
            summary="Would list workspace",
            data={},
            error_code=None,
            error_message=None,
            started_at=started_at,
            finished_at=_utc_now(),
        )
        return result

    return ToolResult(
        ok=False,
        tool_name=tool_request.tool_name,
        execution_id=str(uuid4()),
        summary=f"Unsupported tool: {tool_request.tool_name}",
        data=None,
        error_code="UNSUPPORTED_TOOL",
        error_message=f"Tool not implemented: {tool_request.tool_name}",
        started_at=started_at,
        finished_at=_utc_now(),
    )
