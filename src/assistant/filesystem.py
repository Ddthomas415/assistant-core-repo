from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from assistant.models import ToolRequest, ToolResult

MAX_READ_BYTES = 1024 * 1024
MAX_WORKSPACE_FILES = 200


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _invalid_path_result(tool_name: str, started_at: str) -> ToolResult:
    return ToolResult(
        ok=False,
        tool_name=tool_name,
        execution_id=str(uuid4()),
        summary="Operation failed: invalid path.",
        error_code="invalid_path",
        error_message="Tool argument 'path' must be a non-empty string.",
        started_at=started_at,
        finished_at=utc_now_iso(),
    )


def _outside_workspace_result(tool_name: str, path: Path, workspace_root: Path, started_at: str) -> ToolResult:
    return ToolResult(
        ok=False,
        tool_name=tool_name,
        execution_id=str(uuid4()),
        summary=f"Operation failed: path is outside workspace: {path}",
        error_code="path_outside_workspace",
        error_message=f"Resolved path '{path}' is outside workspace root '{workspace_root}'.",
        started_at=started_at,
        finished_at=utc_now_iso(),
    )


def _resolve_workspace_root(value: object) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value).expanduser().resolve()


def _resolve_target_path(tool_name: str, request: ToolRequest, started_at: str) -> tuple[Path | None, ToolResult | None]:
    path_value = request.arguments.get("path")

    if not isinstance(path_value, str) or not path_value.strip():
        return None, _invalid_path_result(tool_name, started_at)

    try:
        raw_path = Path(path_value).expanduser()
        workspace_root = _resolve_workspace_root(request.arguments.get("workspace_root"))
        if workspace_root is not None and not raw_path.is_absolute():
            path = (workspace_root / raw_path).resolve(strict=False)
        else:
            path = raw_path.resolve(strict=False)
    except OSError as exc:
        return None, ToolResult(
            ok=False,
            tool_name=tool_name,
            execution_id=str(uuid4()),
            summary=f"Operation failed: {exc}",
            error_code="os_error",
            error_message=str(exc),
            started_at=started_at,
            finished_at=utc_now_iso(),
        )

    if workspace_root is not None:
        try:
            path.relative_to(workspace_root)
        except ValueError:
            return None, _outside_workspace_result(tool_name, path, workspace_root, started_at)

    return path, None


def read_file_tool(request: ToolRequest) -> ToolResult:
    started_at = utc_now_iso()
    path, error = _resolve_target_path(request.tool_name, request, started_at)
    if error is not None:
        return error
    assert path is not None

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
        size_bytes = path.stat().st_size
        if size_bytes > MAX_READ_BYTES:
            return ToolResult(
                ok=False,
                tool_name=request.tool_name,
                execution_id=str(uuid4()),
                summary=f"Read failed: file too large: {path}",
                error_code="file_too_large",
                error_message=f"File exceeds max read size of {MAX_READ_BYTES} bytes: {path}",
                started_at=started_at,
                finished_at=utc_now_iso(),
            )

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
            "size_bytes": size_bytes,
        },
        started_at=started_at,
        finished_at=utc_now_iso(),
    )


def write_file_tool(request: ToolRequest) -> ToolResult:
    started_at = utc_now_iso()
    path, error = _resolve_target_path(request.tool_name, request, started_at)
    if error is not None:
        return error
    assert path is not None

    content_value = request.arguments.get("content")
    if not isinstance(content_value, str):
        return ToolResult(
            ok=False,
            tool_name=request.tool_name,
            execution_id=str(uuid4()),
            summary="Write failed: invalid content.",
            error_code="invalid_content",
            error_message="Tool argument 'content' must be a string.",
            started_at=started_at,
            finished_at=utc_now_iso(),
        )

    if path.exists() and not path.is_file():
        return ToolResult(
            ok=False,
            tool_name=request.tool_name,
            execution_id=str(uuid4()),
            summary=f"Write failed: not a file: {path}",
            error_code="not_a_file",
            error_message=f"Path is not a regular file: {path}",
            started_at=started_at,
            finished_at=utc_now_iso(),
        )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content_value, encoding="utf-8")
    except OSError as exc:
        return ToolResult(
            ok=False,
            tool_name=request.tool_name,
            execution_id=str(uuid4()),
            summary=f"Write failed: {exc}",
            error_code="os_error",
            error_message=str(exc),
            started_at=started_at,
            finished_at=utc_now_iso(),
        )

    return ToolResult(
        ok=True,
        tool_name=request.tool_name,
        execution_id=str(uuid4()),
        summary=f"Wrote {path}",
        data={
            "path": str(path),
            "content": content_value,
            "size_bytes": path.stat().st_size,
        },
        started_at=started_at,
        finished_at=utc_now_iso(),
    )

def list_workspace_tool(request: ToolRequest) -> ToolResult:
    started_at = utc_now_iso()

    workspace_root = _resolve_workspace_root(request.arguments.get("workspace_root"))
    if workspace_root is None:
        return ToolResult(
            ok=False,
            tool_name=request.tool_name,
            execution_id=str(uuid4()),
            summary="List failed: no workspace root configured.",
            error_code="no_workspace_root",
            error_message="workspace_root argument is required for list_workspace.",
            started_at=started_at,
            finished_at=utc_now_iso(),
        )

    if not workspace_root.exists():
        return ToolResult(
            ok=False,
            tool_name=request.tool_name,
            execution_id=str(uuid4()),
            summary=f"List failed: workspace not found: {workspace_root}",
            error_code="workspace_not_found",
            error_message=f"Workspace root does not exist: {workspace_root}",
            started_at=started_at,
            finished_at=utc_now_iso(),
        )

    try:
        files = []
        truncated = False
        for p in sorted(workspace_root.rglob("*")):
            if not p.is_file():
                continue
            files.append(str(p.relative_to(workspace_root)))
            if len(files) >= MAX_WORKSPACE_FILES:
                truncated = True
                break
    except OSError as exc:
        return ToolResult(
            ok=False,
            tool_name=request.tool_name,
            execution_id=str(uuid4()),
            summary=f"List failed: {exc}",
            error_code="os_error",
            error_message=str(exc),
            started_at=started_at,
            finished_at=utc_now_iso(),
        )

    listing = "\n".join(files) if files else "(empty)"
    if truncated:
        listing += f"\n... [truncated at {MAX_WORKSPACE_FILES} files]"
    summary = f"Workspace: {workspace_root}\n" + listing
    return ToolResult(
        ok=True,
        tool_name=request.tool_name,
        execution_id=str(uuid4()),
        summary=summary,
        data={"workspace_root": str(workspace_root), "files": files, "truncated": truncated},
        started_at=started_at,
        finished_at=utc_now_iso(),
    )
