"""
MCP (Model Context Protocol) client.

Connects to external MCP servers defined in mcp_servers.json and exposes
their tools to the assistant's tool registry.

Config file format (mcp_servers.json):
{
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
    "transport": "stdio"
  },
  "github": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": { "GITHUB_TOKEN": "..." },
    "transport": "stdio"
  }
}

Usage in tool_registry:
  result = mcp_invoke("filesystem", "read_file", {"path": "..."})
  tools  = mcp_list_tools("filesystem")
  all_tools = mcp_list_all_tools()
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path("mcp_servers.json")


def _load_config() -> dict[str, Any]:
    """Load MCP server config. Returns empty dict if file doesn't exist."""
    if not _CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def mcp_list_tools(server_name: str) -> list[dict[str, Any]]:
    """List tools available on a named MCP server."""
    cfg = _load_config()
    if server_name not in cfg:
        raise ValueError(f"MCP server '{server_name}' not in mcp_servers.json")
    return asyncio.run(_list_tools_async(server_name, cfg[server_name]))


def mcp_list_all_tools() -> dict[str, list[dict[str, Any]]]:
    """Return all tools from all configured MCP servers."""
    cfg = _load_config()
    result: dict[str, list[dict[str, Any]]] = {}
    for name, server_cfg in cfg.items():
        try:
            result[name] = asyncio.run(_list_tools_async(name, server_cfg))
        except Exception as exc:
            result[name] = [{"name": "__error__", "description": str(exc)}]
    return result


def mcp_invoke(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Invoke a tool on an MCP server. Returns {text, isError}."""
    cfg = _load_config()
    if server_name not in cfg:
        return {"text": f"MCP server '{server_name}' not configured.", "isError": True}
    try:
        return asyncio.run(_invoke_async(cfg[server_name], tool_name, arguments or {}))
    except Exception as exc:
        return {"text": str(exc), "isError": True}


# ---------------------------------------------------------------------------
# Async internals
# ---------------------------------------------------------------------------


async def _list_tools_async(
    name: str,
    server_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        from mcp import ClientSession  # noqa: PLC0415
        from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: PLC0415
    except ImportError:
        return [{"name": "__error__", "description": "mcp package not installed: pip install mcp"}]

    params = _make_params(server_cfg)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            tools = getattr(result, "tools", result)
            return [
                {
                    "name":        getattr(t, "name", ""),
                    "description": getattr(t, "description", ""),
                    "inputSchema": getattr(t, "inputSchema", {}),
                }
                for t in tools
            ]


async def _invoke_async(
    server_cfg: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    try:
        from mcp import ClientSession  # noqa: PLC0415
        from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: PLC0415
    except ImportError:
        return {"text": "mcp package not installed: pip install mcp", "isError": True}

    params = _make_params(server_cfg)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(tool_name, arguments)

            raw   = getattr(res, "content", None)
            error = getattr(res, "isError", False)
            text  = _flatten(raw)
            return {"text": text, "isError": error}


def _make_params(server_cfg: dict[str, Any]) -> Any:
    from mcp.client.stdio import StdioServerParameters  # noqa: PLC0415

    command = str(server_cfg.get("command", ""))
    if os.name == "nt" and command.lower() == "npx":
        command = "npx.cmd"

    if shutil.which(command) is None:
        raise FileNotFoundError(
            f"MCP command not found on PATH: '{command}'. "
            "Ensure Node.js / npx is installed."
        )

    raw_args = server_cfg.get("args") or []
    args = [os.path.expanduser(str(a)) for a in raw_args]
    env  = server_cfg.get("env") or None
    return StdioServerParameters(command=command, args=args, env=env)


def _flatten(content: Any) -> str:
    if content is None:     return ""
    if isinstance(content, str): return content
    if isinstance(content, list):
        return "\n".join(_flatten(i) for i in content if _flatten(i))
    if isinstance(content, dict):
        return str(content.get("text") or content.get("data") or content)
    return str(content)
