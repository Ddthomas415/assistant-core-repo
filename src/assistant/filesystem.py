from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from assistant.models import ToolRequest, ToolResult


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_file_tool(request: ToolRequest) -> ToolResult:
    started_at = utc_now_iso()
    path_value = request.arguments.get("path")

    if not isinstance(path_value, str) or not path_value.strip():
        return ToolResult(
            ok=False,
            tool_name=request.tool_name,
            execution_id=str(uuid4()),
            summary="Read failed: invalid path.",
            error_code="invalid_path",
            error_message="Tool argument 'path' must be a non-empty string.",
            started_at=started_at,
            finished_at=utc_now_iso(),
        )

    path = Path(path_value).expanduser()

    if not path.exists():
        return ToolResult(
            ok=False,
            tool_name=request.tool_name,
            execution_id=str(uuid4()),
            summary=f"Read failed: file not found: {path}",
            error_code="file_not_found",
            error_message=f"File does not exist: {path}",
            started_at=started_at,
            finished_at=utc_now_iso(),
        )

    if not path.is_file():
        return ToolResult(
            ok=False,
            tool_name=request.tool_name,
            execution_id=str(uuid4()),
            summary=f"Read failed: not a file: {path}",
            error_code="not_a_file",
            error_message=f"Path is not a regular file: {path}",
            started_at=started_at,
            finished_at=utc_now_iso(),
        )

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ToolResult(
            ok=False,
            tool_name=request.tool_name,
            execution_id=str(uuid4()),
            summary=f"Read failed: file is not valid UTF-8 text: {path}",
            error_code="decode_error",
            error_message=f"Could not decode file as UTF-8: {path}",
            started_at=started_at,
            finished_at=utc_now_iso(),
        )
    except OSError as exc:
        return ToolResult(
            ok=False,
            tool_name=request.tool_name,
            execution_id=str(uuid4()),
            summary=f"Read failed: {exc}",
            error_code="os_error",
            error_message=str(exc),
            started_at=started_at,
            finished_at=utc_now_iso(),
        )

    preview = content if len(content) <= 500 else content[:500] + "\n... [truncated]"
    return ToolResult(
        ok=True,
        tool_name=request.tool_name,
        execution_id=str(uuid4()),
        summary=f"Read {path}\n{preview}",
        data={
            "path": str(path),
            "content": content,
            "size_bytes": path.stat().st_size,
        },
        started_at=started_at,
        finished_at=utc_now_iso(),
    )
