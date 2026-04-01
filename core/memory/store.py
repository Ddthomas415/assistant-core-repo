"""
Long-term memory store.

SQLite-backed, lives in .assistant_memory/memory.db relative to the
project root. No LLM dependency — pure stdlib. The extractor (LLM) and
retriever (search) are separate modules that sit on top of this.

Schema:
    facts(id, content, keywords, source_session_id, created_at)

Keyword search uses SQLite LIKE — no embeddings, fast, good enough for
a personal assistant's memory volume. Swap in a vector store later if
needed without changing the public API.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

MEMORY_DIR = Path(".assistant_memory")

# Minimum token-overlap ratio to consider two facts duplicates.
# 0.70 = 70% of the shorter fact's tokens appear in the existing fact.
_DEDUP_THRESHOLD = 0.70
DB_PATH    = MEMORY_DIR / "memory.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id                 TEXT PRIMARY KEY,
    content            TEXT NOT NULL,
    keywords           TEXT NOT NULL,
    source_session_id  TEXT,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_keywords ON facts(keywords);
"""


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class Fact:
    __slots__ = ("id", "content", "keywords", "source_session_id", "created_at")

    def __init__(
        self,
        id: str,
        content: str,
        keywords: str,
        source_session_id: str | None,
        created_at: str,
    ) -> None:
        self.id                = id
        self.content           = content
        self.keywords          = keywords
        self.source_session_id = source_session_id
        self.created_at        = created_at

    def __repr__(self) -> str:
        return f"Fact({self.id[:8]}… {self.content[:60]!r})"


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


def _connect() -> sqlite3.Connection:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------



def _is_duplicate(content: str) -> bool:
    """
    Return True if a sufficiently similar fact already exists in the store.

    Uses token-overlap (Jaccard-style): if the fraction of the new fact's
    meaningful tokens that appear in any existing fact's content exceeds
    _DEDUP_THRESHOLD, the fact is considered a duplicate.
    """
    tokens = set(_derive_keywords(content))
    if not tokens:
        return False

    with _connect() as conn:
        rows = conn.execute(
            "SELECT content FROM facts ORDER BY created_at DESC LIMIT 200"
        ).fetchall()

    for row in rows:
        existing_tokens = set(_derive_keywords(row["content"]))
        if not existing_tokens:
            continue
        overlap = len(tokens & existing_tokens) / len(tokens)
        if overlap >= _DEDUP_THRESHOLD:
            return True
    return False


def save_fact(
    content: str,
    *,
    source_session_id: str | None = None,
    keywords: list[str] | None = None,
) -> Fact:
    """
    Persist a single fact.

    keywords — explicit list; if omitted, auto-derived from content.
    Returns the saved Fact.
    """
    content = content.strip()
    if not content:
        raise ValueError("content must not be empty")

    if _is_duplicate(content):
        # Return a sentinel fact without persisting.
        return Fact(id="", content=content, keywords="", source_session_id=None, created_at="")

    kw_list = keywords if keywords is not None else _derive_keywords(content)
    kw_str  = ",".join(kw_list).lower()
    now     = _utc_now()
    fid     = str(uuid4())

    with _connect() as conn:
        conn.execute(
            "INSERT INTO facts (id, content, keywords, source_session_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (fid, content, kw_str, source_session_id, now),
        )

    return Fact(
        id=fid,
        content=content,
        keywords=kw_str,
        source_session_id=source_session_id,
        created_at=now,
    )


def save_facts(
    contents: list[str],
    *,
    source_session_id: str | None = None,
) -> list[Fact]:
    """Persist multiple facts in a single transaction."""
    if not contents:
        return []

    now  = _utc_now()
    rows = []
    facts: list[Fact] = []

    for content in contents:
        content = content.strip()
        if not content:
            continue
        if _is_duplicate(content):
            continue
        fid    = str(uuid4())
        kw_str = ",".join(_derive_keywords(content)).lower()
        rows.append((fid, content, kw_str, source_session_id, now))
        facts.append(Fact(fid, content, kw_str, source_session_id, now))

    if rows:
        with _connect() as conn:
            conn.executemany(
                "INSERT INTO facts (id, content, keywords, source_session_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )

    return facts


def delete_fact(fact_id: str) -> bool:
    """Delete a fact by ID. Returns True if a row was deleted."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        return cur.rowcount > 0


def clear_all() -> int:
    """Delete every fact. Returns count deleted. Use with care."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM facts")
        return cur.rowcount


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


def search(query: str, *, limit: int = 8) -> list[Fact]:
    """
    Return up to `limit` facts relevant to `query`.

    Matching strategy:
      - Split query into tokens (≥3 chars, stop-words removed).
      - Rank facts by how many tokens appear in their content or keywords.
      - Ties broken by newest first.
    """
    tokens = _query_tokens(query)
    if not tokens:
        return []

    with _connect() as conn:
        # Fetch all facts and score client-side (fast enough for personal
        # memory volumes; swap to FTS5 if the store grows beyond ~100k rows).
        rows = conn.execute(
            "SELECT id, content, keywords, source_session_id, created_at "
            "FROM facts ORDER BY created_at DESC"
        ).fetchall()

    scored: list[tuple[int, Fact]] = []
    for row in rows:
        content_lower  = row["content"].lower()
        keywords_lower = row["keywords"].lower()
        score = sum(
            1 for t in tokens
            if t in content_lower or t in keywords_lower
        )
        if score > 0:
            scored.append((
                score,
                Fact(
                    id=row["id"],
                    content=row["content"],
                    keywords=row["keywords"],
                    source_session_id=row["source_session_id"],
                    created_at=row["created_at"],
                ),
            ))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:limit]]


def get_all(*, limit: int = 200) -> list[Fact]:
    """Return all stored facts, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, keywords, source_session_id, created_at "
            "FROM facts ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        Fact(
            id=r["id"],
            content=r["content"],
            keywords=r["keywords"],
            source_session_id=r["source_session_id"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def count() -> int:
    """Return total number of stored facts."""
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]


# ---------------------------------------------------------------------------
# Keyword helpers
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "i", "me", "my", "you", "your", "he", "she", "it", "we", "they",
    "that", "this", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "not", "no", "so", "as",
}


def _derive_keywords(text: str) -> list[str]:
    """Extract meaningful tokens from text for keyword indexing."""
    words = text.lower().replace(",", " ").replace(".", " ").replace(":", " ").split()
    return [w for w in words if len(w) >= 3 and w not in _STOP_WORDS]


def _query_tokens(query: str) -> list[str]:
    """Tokenise a search query the same way as _derive_keywords."""
    return _derive_keywords(query)
