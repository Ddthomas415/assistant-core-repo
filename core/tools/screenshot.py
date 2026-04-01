"""
Screenshot and vision tool.

Takes a screenshot, saves it to workspace/, and optionally sends it to
the LLM for visual analysis.

Requires: pip install Pillow
Optional:  pip install pyautogui  (for full-screen capture)
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path("workspace").resolve()


def take_screenshot() -> dict[str, Any]:
    """
    Capture the screen and save to workspace/screenshots/.

    Returns:
        {
            "path":     str,   relative path inside workspace
            "filename": str,
            "base64":   str,   base64-encoded PNG for vision API
            "error":    str | None,
        }
    """
    try:
        from PIL import ImageGrab  # noqa: PLC0415
    except ImportError:
        return _error("Pillow not installed. Run: pip install Pillow")

    try:
        out_dir = WORKSPACE_ROOT / "screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)

        ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{ts}.png"
        full_path = out_dir / filename

        img = ImageGrab.grab()
        img.save(str(full_path), format="PNG")

        with open(full_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        rel_path = str(full_path.relative_to(WORKSPACE_ROOT))
        return {
            "path":     rel_path,
            "filename": filename,
            "base64":   b64,
            "error":    None,
        }
    except Exception as exc:
        return _error(str(exc))


def analyze_screenshot(base64_image: str, question: str | None = None) -> dict[str, Any]:
    """
    Send a base64 PNG to the LLM vision API and return analysis.

    Returns:
        {
            "analysis": str,
            "error":    str | None,
        }
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"analysis": "", "error": "ANTHROPIC_API_KEY not set — vision analysis unavailable."}

    prompt = question or "Describe what you see on this screen."

    try:
        import requests  # noqa: PLC0415
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      os.getenv("ASSISTANT_MODEL", "claude-haiku-4-5-20251001"),
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type":   "image",
                                "source": {
                                    "type":       "base64",
                                    "media_type": "image/png",
                                    "data":       base64_image,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json().get("content", [])
        text    = "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
        return {"analysis": text, "error": None}
    except Exception as exc:
        return {"analysis": "", "error": str(exc)}


def _error(msg: str) -> dict[str, Any]:
    return {"path": "", "filename": "", "base64": "", "error": msg}
