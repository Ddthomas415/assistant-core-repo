from __future__ import annotations

import difflib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from assistant.models import ToolRequest, ToolResult

MAX_READ_BYTES = 64 * 1024
MAX_WORKSPACE_FILES = 50


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result(
    *,
    ok: bool,
    tool_name: str,
    summary: str,
    data: dict | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    started_at: str,
) -> ToolResult:
    return ToolResult(
        ok=ok,
        tool_name=tool_name,
        execution_id=str(uuid4()),
        summary=summary,
        data=data or {},
        error_code=error_code,
        error_message=error_message,
        started_at=started_at,
        finished_at=utc_now_iso(),
    )


def _resolve_workspace_root(value: object) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value).expanduser().resolve(strict=False)


def _resolve_target_path(
    tool_name: str,
    request: ToolRequest,
    started_at: str,
) -> tuple[Path | None, Path | None, ToolResult | None]:
    path_value = request.arguments.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        return None, None, _result(
            ok=False,
            tool_name=tool_name,
            summary="Operation failed: invalid path.",
            error_code="invalid_path",
            error_message="Tool argument 'path' must be a non-empty string.",
            started_at=started_at,
        )

    workspace_root = _resolve_workspace_root(request.arguments.get("workspace_root"))
    raw_path = Path(path_value).expanduser()

    try:
        if workspace_root is not None:
            candidate = raw_path if raw_path.is_absolute() else workspace_root / raw_path
            resolved = candidate.resolve(strict=False)
            try:
                resolved.relative_to(workspace_root)
            except ValueError:
                return None, workspace_root, _result(
                    ok=False,
                    tool_name=tool_name,
                    summary=f"Operation failed: path is outside workspace: {resolved}",
                    error_code="path_outside_workspace",
                    error_message=f"Resolved path '{resolved}' is outside workspace root '{workspace_root}'.",
                    data={"path": str(resolved), "workspace_root": str(workspace_root)},
                    started_at=started_at,
                )
            return resolved, workspace_root, None

        resolved = raw_path.resolve(strict=False)
        return resolved, None, None

    except OSError as exc:
        return None, workspace_root, _result(
            ok=False,
            tool_name=tool_name,
            summary=f"Operation failed: {exc}",
            error_code="os_error",
            error_message=str(exc),
            started_at=started_at,
        )


def _should_ignore_suggestion_path(relative_path: str) -> bool:
    parts = relative_path.split("/")
    ignored_prefixes = {
        ".git",
        ".venv",
        ".assistant_sessions",
        ".assistant_sessions_demo",
        "__pycache__",
        ".pytest_cache",
        ".github",
    }
    ignored_filenames = {
        ".DS_Store",
    }
    return (
        any(part in ignored_prefixes for part in parts)
        or any(part.endswith(".egg-info") for part in parts)
        or parts[-1] in ignored_filenames
    )


def _find_nearby_workspace_matches(
    workspace_root: Path,
    requested_path: Path,
    allowed_names: list[str] | None = None,
) -> list[str]:
    requested_name = requested_path.name
    if not requested_name:
        return []

    try:
        candidates = sorted(
            relative_path
            for relative_path in (
                str(p.relative_to(workspace_root)).replace("\\", "/")
                for p in workspace_root.rglob("*")
                if p.is_file()
            )
            if not _should_ignore_suggestion_path(relative_path)
        )
    except OSError:
        return []

    if allowed_names is not None:
        allowed = {name.lower() for name in allowed_names}
        candidates = [candidate for candidate in candidates if candidate.lower() in allowed]

    if not candidates:
        return []

    name_map = {candidate.split("/")[-1]: candidate for candidate in candidates}
    close_names = difflib.get_close_matches(requested_name, list(name_map.keys()), n=3, cutoff=0.5)

    ordered: list[str] = []
    for name in close_names:
        candidate = name_map[name]
        if candidate not in ordered:
            ordered.append(candidate)

    return ordered


def read_file_tool(request: ToolRequest) -> ToolResult:
    started_at = utc_now_iso()
    path, workspace_root, error = _resolve_target_path(request.tool_name, request, started_at)
    if error is not None:
        return error
    assert path is not None

    if not path.exists():
        suggestions: list[str] = []
        if workspace_root is not None:
            suggestion_names = request.arguments.get("suggestion_names")
            allowed_names = suggestion_names if isinstance(suggestion_names, list) else None
            suggestions = _find_nearby_workspace_matches(workspace_root, path, allowed_names=allowed_names)

        summary = f"Read failed: file not found: {path}"
        if suggestions:
            summary += "\nDid you mean:\n" + "\n".join(suggestions)

        return _result(
            ok=False,
            tool_name=request.tool_name,
            summary=summary,
            error_code="file_not_found",
            error_message=f"File does not exist: {path}",
            data={
                "path": str(path),
                "workspace_root": str(workspace_root) if workspace_root else None,
                "suggestions": suggestions,
            },
            started_at=started_at,
        )

    if not path.is_file():
        return _result(
            ok=False,
            tool_name=request.tool_name,
            summary=f"Read failed: not a file: {path}",
            error_code="not_a_file",
            error_message=f"Path is not a regular file: {path}",
            data={
                "path": str(path),
                "workspace_root": str(workspace_root) if workspace_root else None,
            },
            started_at=started_at,
        )

    try:
        raw = path.read_bytes()
    except OSError as exc:
        return _result(
            ok=False,
            tool_name=request.tool_name,
            summary=f"Read failed: {exc}",
            error_code="os_error",
            error_message=str(exc),
            data={"path": str(path)},
            started_at=started_at,
        )

    if len(raw) > MAX_READ_BYTES:
        return _result(
            ok=False,
            tool_name=request.tool_name,
            summary=f"Read failed: file too large: {path}",
            error_code="file_too_large",
            error_message=f"File exceeds MAX_READ_BYTES={MAX_READ_BYTES}",
            data={"path": str(path), "size_bytes": len(raw)},
            started_at=started_at,
        )

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _result(
            ok=False,
            tool_name=request.tool_name,
            summary=f"Read failed: file is not valid UTF-8 text: {path}",
            error_code="decode_error",
            error_message=f"Could not decode file as UTF-8: {path}",
            data={"path": str(path)},
            started_at=started_at,
        )

    preview = content if len(content) <= 500 else content[:500] + "\n... [truncated]"

    return _result(
        ok=True,
        tool_name=request.tool_name,
        summary=f"Read {path}\n{preview}",
        data={
            "path": str(path),
            "content": content,
            "size_bytes": path.stat().st_size,
        },
        started_at=started_at,
    )


def write_file_tool(request: ToolRequest) -> ToolResult:
    started_at = utc_now_iso()
    path, workspace_root, error = _resolve_target_path(request.tool_name, request, started_at)
    if error is not None:
        return error
    assert path is not None

    content = request.arguments.get("content")
    if not isinstance(content, str):
        return _result(
            ok=False,
            tool_name=request.tool_name,
            summary="Write failed: invalid content.",
            error_code="invalid_content",
            error_message="Tool argument 'content' must be a string.",
            data={"path": str(path)},
            started_at=started_at,
        )

    if path.exists() and not path.is_file():
        return _result(
            ok=False,
            tool_name=request.tool_name,
            summary=f"Write failed: not a file: {path}",
            error_code="not_a_file",
            error_message=f"Path is not a regular file: {path}",
            data={
                "path": str(path),
                "workspace_root": str(workspace_root) if workspace_root else None,
            },
            started_at=started_at,
        )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return _result(
            ok=False,
            tool_name=request.tool_name,
            summary=f"Write failed: {exc}",
            error_code="os_error",
            error_message=str(exc),
            data={"path": str(path)},
            started_at=started_at,
        )

    return _result(
        ok=True,
        tool_name=request.tool_name,
        summary=f"Wrote {path}",
        data={
            "path": str(path),
            "content": content,
            "size_bytes": path.stat().st_size,
        },
        started_at=started_at,
    )


def list_workspace_tool(request: ToolRequest) -> ToolResult:
    started_at = utc_now_iso()
    workspace_root_value = request.arguments.get("workspace_root")

    if not isinstance(workspace_root_value, str) or not workspace_root_value.strip():
        return _result(
            ok=False,
            tool_name=request.tool_name,
            summary="List failed: workspace root is required.",
            error_code="no_workspace_root",
            error_message="Tool argument 'workspace_root' must be provided.",
            started_at=started_at,
        )

    root = Path(workspace_root_value).expanduser().resolve(strict=False)

    if not root.exists():
        return _result(
            ok=False,
            tool_name=request.tool_name,
            summary=f"List failed: workspace root not found: {root}",
            error_code="workspace_not_found",
            error_message=f"Workspace root does not exist: {root}",
            data={"workspace_root": str(root)},
            started_at=started_at,
        )

    if not root.is_dir():
        return _result(
            ok=False,
            tool_name=request.tool_name,
            summary=f"List failed: workspace root is not a directory: {root}",
            error_code="workspace_not_directory",
            error_message=f"Workspace root is not a directory: {root}",
            data={"workspace_root": str(root)},
            started_at=started_at,
        )

    try:
        files = sorted(
            relative_path
            for relative_path in (
                str(p.relative_to(root)).replace("\\", "/")
                for p in root.rglob("*")
                if p.is_file()
            )
            if not _should_ignore_suggestion_path(relative_path)
        )
    except OSError as exc:
        return _result(
            ok=False,
            tool_name=request.tool_name,
            summary=f"List failed: {exc}",
            error_code="os_error",
            error_message=str(exc),
            data={"workspace_root": str(root)},
            started_at=started_at,
        )

    truncated = len(files) > MAX_WORKSPACE_FILES
    visible_files = files[:MAX_WORKSPACE_FILES]

    if visible_files:
        file_count = len(visible_files)
        noun = "file" if file_count == 1 else "files"
        summary = f"Workspace files ({file_count} {noun}):\n" + "\n".join(visible_files)
    else:
        summary = "Workspace is empty."

    if truncated:
        summary += f"\n... truncated at {MAX_WORKSPACE_FILES} files"

    return _result(
        ok=True,
        tool_name=request.tool_name,
        summary=summary,
        data={
            "workspace_root": str(root),
            "files": visible_files,
            "truncated": truncated,
        },
        started_at=started_at,
    )
