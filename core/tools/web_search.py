"""
DuckDuckGo web search — no API key required.

Two-pass approach:
  1. DDG instant API  → structured answer if the query has one
  2. DDG Lite scrape  → up to max_results title + URL pairs
  3. Auto-fetch       → text content of the top result (only when no instant answer)
"""
from __future__ import annotations

import urllib.parse
from typing import Any

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def search(query: str, max_results: int = 5) -> dict[str, Any]:
    """
    Search DuckDuckGo and return structured results.

    Returns:
        {
            "query":    str,
            "instant":  str | None,                        # DDG instant answer
            "results":  [{"title": str, "url": str}, ...], # web links
            "fetched":  str | None,                        # content from top result
        }
    """
    instant = _ddg_instant(query)
    links = _ddg_lite(query, max_results)

    fetched = None
    if links and not instant:
        fetched = _fetch_content(links[0]["url"], max_chars=3_000)

    return {
        "query":   query,
        "instant": instant,
        "results": links,
        "fetched": fetched,
    }


def format_results(data: dict[str, Any]) -> str:
    """Convert search result dict into a human-readable string for the assistant message."""
    lines: list[str] = []

    if data.get("instant"):
        lines.append(f"Answer: {data['instant']}")
        lines.append("")

    if data.get("fetched"):
        lines.append("Content from top result:")
        lines.append(data["fetched"])
        lines.append("")

    results = data.get("results", [])
    if results:
        lines.append(f"Search results for \"{data['query']}\":")
        for i, r in enumerate(results, 1):
            lines.append(f"  {i}. {r['title']}")
            lines.append(f"     {r['url']}")

    if not lines:
        lines.append(f"No results found for \"{data['query']}\".")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ddg_instant(query: str) -> str | None:
    """Hit the DDG JSON instant-answer API. Returns a plain-text answer or None."""
    try:
        import requests  # noqa: PLC0415
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            headers=_HEADERS,
            timeout=5,
        )
        r.raise_for_status()
        d = r.json()
        return d.get("Abstract") or d.get("Answer") or d.get("Definition") or None
    except Exception:
        return None


def _ddg_lite(query: str, max_results: int) -> list[dict[str, str]]:
    """Scrape DDG Lite and return up to max_results {title, url} dicts."""
    try:
        import requests  # noqa: PLC0415
        from bs4 import BeautifulSoup  # noqa: PLC0415

        encoded = urllib.parse.quote_plus(query)
        r = requests.get(
            f"https://lite.duckduckgo.com/lite/?q={encoded}",
            headers=_HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.content, "html.parser")
        results: list[dict[str, str]] = []

        for link in soup.find_all("a", href=True):
            if len(results) >= max_results:
                break

            href: str = link.get("href", "")
            title: str = link.get_text().strip()

            # Decode DDG redirect URLs
            if "duckduckgo.com/l/" in href and "uddg=" in href:
                try:
                    qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    href = urllib.parse.unquote(qs["uddg"][0])
                except Exception:
                    continue

            if (
                href.startswith("http")
                and len(title) > 10
                and not any(s in title.lower() for s in ("settings", "privacy", "about", "help"))
            ):
                results.append({"title": title, "url": href})

        return results
    except ImportError:
        return []
    except Exception:
        return []


def _fetch_content(url: str, max_chars: int = 3_000) -> str | None:
    """Fetch a URL and return clean plain text, or None on failure."""
    try:
        import requests  # noqa: PLC0415
        from bs4 import BeautifulSoup  # noqa: PLC0415

        r = requests.get(url, headers=_HEADERS, timeout=8, allow_redirects=True)
        r.raise_for_status()

        soup = BeautifulSoup(r.content, "html.parser")
        for tag in soup(["script", "style", "meta", "link", "noscript", "nav", "footer", "header", "aside"]):
            tag.decompose()

        lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if len(l.strip()) > 3]

        # Deduplicate consecutive identical lines
        deduped: list[str] = []
        prev = None
        for line in lines:
            if line != prev:
                deduped.append(line)
                prev = line

        content = "\n".join(deduped)
        return (content[:max_chars] + "…") if len(content) > max_chars else content or None
    except Exception:
        return None
