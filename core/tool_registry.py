from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.types import ToolRequest, ToolResult

WORKSPACE_ROOT = Path("workspace").resolve()


def _utc_now() -> str:
    """Return a UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_workspace() -> None:
    """Ensure the workspace root exists."""
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)


def _resolve_workspace_path(filename: str) -> Path:
    """
    Resolve a filename safely inside the workspace root.

    Prevents path traversal outside the workspace.
    """
    _ensure_workspace()
    candidate = (WORKSPACE_ROOT / filename).resolve()

    if candidate == WORKSPACE_ROOT or str(candidate).startswith(str(WORKSPACE_ROOT) + "/"):
        return candidate

    raise PermissionError(f"Path not allowed: {filename}")


def _list_workspace_data() -> dict:
    """Return a structured list of files under the workspace."""
    _ensure_workspace()
    files = []
    for path in sorted(WORKSPACE_ROOT.rglob("*")):
        if path.is_file():
            files.append(str(path.relative_to(WORKSPACE_ROOT)))
    return {"files": files}


def execute_tool_request(tool_request: ToolRequest) -> ToolResult:
    """
    Execute a tool request using the current assistant-core tool surface.

    Supported tools:
    - read_file
    - list_workspace
    - write_file
    - edit_file
    """
    started_at = _utc_now()

    try:
        if tool_request.tool_name == "read_file":
            filename = tool_request.arguments["filename"]
            path = _resolve_workspace_path(filename)

            if not path.exists():
                return ToolResult(
                    ok=False,
                    tool_name="read_file",
                    execution_id=str(uuid4()),
                    summary=f"File not found: {filename}",
                    data=None,
                    error_code="FILE_NOT_FOUND",
                    error_message=f"File not found: {filename}",
                    started_at=started_at,
                    finished_at=_utc_now(),
                )

            content = path.read_text(encoding="utf-8")
            return ToolResult(
                ok=True,
                tool_name="read_file",
                execution_id=str(uuid4()),
                summary=f"Read {filename}",
                data={"filename": filename, "content": content},
                error_code=None,
                error_message=None,
                started_at=started_at,
                finished_at=_utc_now(),
            )

        if tool_request.tool_name == "list_workspace":
            data = _list_workspace_data()
            return ToolResult(
                ok=True,
                tool_name="list_workspace",
                execution_id=str(uuid4()),
                summary=f"Listed {len(data['files'])} workspace file(s)",
                data=data,
                error_code=None,
                error_message=None,
                started_at=started_at,
                finished_at=_utc_now(),
            )

        if tool_request.tool_name == "write_file":
            filename = tool_request.arguments["filename"]
            content = tool_request.arguments.get("content", "")
            path = _resolve_workspace_path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

            return ToolResult(
                ok=True,
                tool_name="write_file",
                execution_id=str(uuid4()),
                summary=f"Wrote {filename}",
                data={"filename": filename, "content": content},
                error_code=None,
                error_message=None,
                started_at=started_at,
                finished_at=_utc_now(),
            )

        if tool_request.tool_name == "edit_file":
            filename = tool_request.arguments["filename"]
            content = tool_request.arguments.get("content", "")
            path = _resolve_workspace_path(filename)

            if not path.exists():
                return ToolResult(
                    ok=False,
                    tool_name="edit_file",
                    execution_id=str(uuid4()),
                    summary=f"File not found: {filename}",
                    data=None,
                    error_code="FILE_NOT_FOUND",
                    error_message=f"File not found: {filename}",
                    started_at=started_at,
                    finished_at=_utc_now(),
                )

            path.write_text(content, encoding="utf-8")
            return ToolResult(
                ok=True,
                tool_name="edit_file",
                execution_id=str(uuid4()),
                summary=f"Edited {filename}",
                data={"filename": filename, "content": content},
                error_code=None,
                error_message=None,
                started_at=started_at,
                finished_at=_utc_now(),
            )

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

    except PermissionError as exc:
        return ToolResult(
            ok=False,
            tool_name=tool_request.tool_name,
            execution_id=str(uuid4()),
            summary="Path not allowed",
            data=None,
            error_code="PATH_NOT_ALLOWED",
            error_message=str(exc),
            started_at=started_at,
            finished_at=_utc_now(),
        )
