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
    - web_search
    - fetch_page
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

        if tool_request.tool_name == "web_search":
            from core.tools.web_search import search  # noqa: PLC0415
            query = tool_request.arguments["query"]
            data = search(query)
            result_count = len(data.get("results", []))
            has_instant = bool(data.get("instant"))
            summary = (
                f"Found instant answer for \"{query}\""
                if has_instant
                else f"Found {result_count} result(s) for \"{query}\""
            )
            return ToolResult(
                ok=True,
                tool_name="web_search",
                execution_id=str(uuid4()),
                summary=summary,
                data=data,
                error_code=None,
                error_message=None,
                started_at=started_at,
                finished_at=_utc_now(),
            )

        if tool_request.tool_name == "fetch_page":
            from core.tools.fetch_page import fetch  # noqa: PLC0415
            url = tool_request.arguments["url"]
            include_links = tool_request.arguments.get("include_links", False)
            data = fetch(url, include_links=include_links)
            if data.get("error"):
                return ToolResult(
                    ok=False,
                    tool_name="fetch_page",
                    execution_id=str(uuid4()),
                    summary=f"Failed to fetch {url}",
                    data=data,
                    error_code="FETCH_FAILED",
                    error_message=data["error"],
                    started_at=started_at,
                    finished_at=_utc_now(),
                )
            content_len = len(data.get("content", ""))
            return ToolResult(
                ok=True,
                tool_name="fetch_page",
                execution_id=str(uuid4()),
                summary=f"Fetched {url} ({content_len} chars)",
                data=data,
                error_code=None,
                error_message=None,
                started_at=started_at,
                finished_at=_utc_now(),
            )


        if tool_request.tool_name == "get_weather":
            from core.tools.weather import get_weather, format_result as fmt_weather  # noqa: PLC0415
            location = tool_request.arguments.get("location")
            data = get_weather(location)
            ok = not bool(data.get("error"))
            return ToolResult(
                ok=ok, tool_name="get_weather", execution_id=str(uuid4()),
                summary=data.get("condition", data.get("error", "")) + f" {data.get('temperature_c','')}°C" if ok else data.get("error",""),
                data=data, error_code=None if ok else "WEATHER_FAILED",
                error_message=None if ok else data.get("error"),
                started_at=started_at, finished_at=_utc_now(),
            )

        if tool_request.tool_name == "execute_code":
            from core.tools.code_exec import execute, format_result as fmt_code  # noqa: PLC0415
            code = tool_request.arguments.get("code", "")
            language = tool_request.arguments.get("language", "python")
            data = execute(code, language=language)
            ok = data.get("exit_code", 1) == 0 and not data.get("timed_out")
            return ToolResult(
                ok=ok, tool_name="execute_code", execution_id=str(uuid4()),
                summary="Executed successfully" if ok else f"Exit {data.get('exit_code',1)}",
                data=data, error_code=None if ok else "EXEC_FAILED",
                error_message=data.get("stderr","")[:200] if not ok else None,
                started_at=started_at, finished_at=_utc_now(),
            )

        if tool_request.tool_name == "take_screenshot":
            from core.tools.screenshot import take_screenshot, analyze_screenshot  # noqa: PLC0415
            data = take_screenshot()
            if data.get("error"):
                return ToolResult(
                    ok=False, tool_name="take_screenshot", execution_id=str(uuid4()),
                    summary=f"Screenshot failed: {data['error']}", data=data,
                    error_code="SCREENSHOT_FAILED", error_message=data["error"],
                    started_at=started_at, finished_at=_utc_now(),
                )
            question = tool_request.arguments.get("question")
            if question and data.get("base64"):
                analysis = analyze_screenshot(data["base64"], question)
                data["analysis"] = analysis.get("analysis", "")
                data["analysis_error"] = analysis.get("error")
            return ToolResult(
                ok=True, tool_name="take_screenshot", execution_id=str(uuid4()),
                summary=f"Screenshot saved: {data.get('filename','')}",
                data=data, error_code=None, error_message=None,
                started_at=started_at, finished_at=_utc_now(),
            )

        if tool_request.tool_name == "mcp_invoke":
            from core.tools.mcp_client import mcp_invoke  # noqa: PLC0415
            server = tool_request.arguments.get("server", "")
            tool   = tool_request.arguments.get("tool", "")
            args   = tool_request.arguments.get("arguments", {})
            result = mcp_invoke(server, tool, args)
            ok = not result.get("isError", False)
            return ToolResult(
                ok=ok, tool_name="mcp_invoke", execution_id=str(uuid4()),
                summary=result.get("text","")[:120],
                data=result, error_code=None if ok else "MCP_ERROR",
                error_message=result.get("text") if not ok else None,
                started_at=started_at, finished_at=_utc_now(),
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
