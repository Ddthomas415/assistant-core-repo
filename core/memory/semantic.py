"""
Semantic memory search using sentence embeddings.

Optional upgrade to core/memory/store.py keyword search.
Uses sentence-transformers (local, offline) if installed.
Falls back to keyword search transparently when not available.

Install:
    pip install sentence-transformers  (~500MB first run, downloads model)

The model is cached in ~/.cache/huggingface after first use.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.memory.store import Fact, _connect, _derive_keywords

_MODEL_NAME    = "all-MiniLM-L6-v2"   # small, fast, good quality
_EMBED_DB_PATH = Path(".assistant_memory") / "embeddings.json"
_SIM_THRESHOLD = 0.72   # cosine similarity to consider semantic match


def semantic_search(query: str, *, limit: int = 8) -> list[Fact]:
    """
    Search memory using semantic similarity.

    Falls back to keyword search if sentence-transformers isn't installed.
    """
    try:
        return _embed_search(query, limit=limit)
    except ImportError:
        from core.memory.store import search  # noqa: PLC0415
        return search(query, limit=limit)
    except Exception:
        from core.memory.store import search  # noqa: PLC0415
        return search(query, limit=limit)


def rebuild_embeddings() -> int:
    """
    Rebuild the embedding index from all stored facts.
    Returns the number of embeddings computed.
    """
    try:
        model = _load_model()
    except ImportError:
        return 0

    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content FROM facts ORDER BY created_at DESC"
        ).fetchall()

    index: dict[str, list[float]] = {}
    texts = [r["content"] for r in rows]
    if not texts:
        _save_index({})
        return 0

    embeddings = model.encode(texts, convert_to_tensor=False).tolist()
    for row, emb in zip(rows, embeddings):
        index[row["id"]] = emb

    _save_index(index)
    return len(index)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _embed_search(query: str, *, limit: int) -> list[Fact]:
    """Run cosine-similarity search over stored embeddings."""
    model = _load_model()
    index = _load_index()

    if not index:
        from core.memory.store import search  # noqa: PLC0415
        return search(query, limit=limit)

    query_emb = model.encode([query], convert_to_tensor=False)[0]

    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, keywords, source_session_id, created_at FROM facts"
        ).fetchall()

    fact_map = {r["id"]: r for r in rows}
    scored: list[tuple[float, Fact]] = []

    for fact_id, fact_emb in index.items():
        if fact_id not in fact_map:
            continue
        sim = _cosine(query_emb, fact_emb)
        if sim >= _SIM_THRESHOLD:
            r = fact_map[fact_id]
            scored.append((sim, Fact(
                id=r["id"],
                content=r["content"],
                keywords=r["keywords"],
                source_session_id=r["source_session_id"],
                created_at=r["created_at"],
            )))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:limit]]


def _cosine(a: list[float], b: list[float]) -> float:
    import math  # noqa: PLC0415
    dot  = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if not mag_a or not mag_b:
        return 0.0
    return dot / (mag_a * mag_b)


def _load_model():
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    return SentenceTransformer(_MODEL_NAME)


def _load_index() -> dict[str, list[float]]:
    if not _EMBED_DB_PATH.exists():
        return {}
    try:
        return json.loads(_EMBED_DB_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_index(index: dict[str, list[float]]) -> None:
    _EMBED_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _EMBED_DB_PATH.write_text(json.dumps(index), encoding="utf-8")
