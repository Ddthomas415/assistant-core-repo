"""
Fetch and extract clean text content from a web page URL.
No API key required — uses requests + BeautifulSoup.
"""
from __future__ import annotations

from typing import Any

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_MAX_CONTENT_CHARS = 10_000
_MAX_LINKS = 20


def fetch(url: str, *, include_links: bool = False) -> dict[str, Any]:
    """
    Fetch a URL and return structured content.

    Returns:
        {
            "url":     str,
            "title":   str | None,
            "content": str,
            "links":   [{"text": str, "href": str}, ...],  # only if include_links=True
            "error":   str | None,
        }
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        import requests  # noqa: PLC0415

        r = requests.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
        r.raise_for_status()

        try:
            from bs4 import BeautifulSoup  # noqa: PLC0415
            return _parse_with_bs4(r, url, include_links=include_links)
        except ImportError:
            # BeautifulSoup not installed — return raw truncated text
            return {
                "url":     url,
                "title":   None,
                "content": r.text[:_MAX_CONTENT_CHARS],
                "links":   [],
                "error":   None,
            }

    except Exception as exc:
        return {
            "url":     url,
            "title":   None,
            "content": "",
            "links":   [],
            "error":   str(exc),
        }


def format_result(data: dict[str, Any]) -> str:
    """Convert fetch result dict into a human-readable string for the assistant message."""
    if data.get("error"):
        return f"Failed to fetch {data['url']}: {data['error']}"

    parts: list[str] = []
    if data.get("title"):
        parts.append(f"Title: {data['title']}")
    parts.append(f"URL: {data['url']}")
    parts.append("")
    parts.append(data.get("content") or "(no content extracted)")

    if data.get("links"):
        parts.append("")
        parts.append("Links found on page:")
        for lnk in data["links"]:
            parts.append(f"  • {lnk['text']}: {lnk['href']}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _parse_with_bs4(response: Any, url: str, *, include_links: bool) -> dict[str, Any]:
    from bs4 import BeautifulSoup  # noqa: PLC0415
    import urllib.parse  # noqa: PLC0415

    soup = BeautifulSoup(response.content, "html.parser")

    for tag in soup(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()

    title: str | None = None
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text().strip() or None

    # Extract and deduplicate text lines
    lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if len(l.strip()) > 3]
    seen: set[str] = set()
    unique: list[str] = []
    for line in lines:
        if line not in seen:
            unique.append(line)
            seen.add(line)
    content = "\n".join(unique[:500])
    if len(content) > _MAX_CONTENT_CHARS:
        content = content[:_MAX_CONTENT_CHARS] + "…"

    links: list[dict[str, str]] = []
    if include_links:
        for a in soup.find_all("a", href=True):
            if len(links) >= _MAX_LINKS:
                break
            href: str = a.get("href", "").strip()
            text: str = a.get_text().strip()
            if not href or not text or len(text) < 3:
                continue
            if href.startswith("/"):
                href = urllib.parse.urljoin(url, href)
            elif not href.startswith(("http://", "https://")):
                continue
            links.append({"text": text, "href": href})

    return {"url": url, "title": title, "content": content, "links": links, "error": None}
