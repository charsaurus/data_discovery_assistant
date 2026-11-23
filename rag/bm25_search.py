"""
BM25 sparse (keyword) search over the catalog, used alongside the dense
vector search for hybrid retrieval. Dense embeddings are good at semantic/
intent matching ("customer buying behaviour"); BM25 is good at exact-term
matching (table names, column names, IDs like "SRC-007" or "customer_id")
that embeddings sometimes blur together.

The corpus is small (one document per catalog source), so we just rebuild
the BM25 index fresh each call — cheap, and always reflects the current
catalog on disk without needing separate persistence/invalidation logic.
"""

from __future__ import annotations

import re
from functools import lru_cache

from rank_bm25 import BM25Okapi

from . import config
from .loaders import build_chunks

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@lru_cache(maxsize=1)
def _build_index(data_dir_str: str):
    """Cached BM25 index + parallel list of (source_filename) for the
    current catalog. Cache key is the data dir path; call
    bm25_search.cache_clear() after re-ingesting if the catalog changes
    within the same process (the Streamlit app re-imports fresh per run,
    so this mainly matters for long-lived processes / tests)."""
    from pathlib import Path

    chunks = build_chunks(Path(data_dir_str))
    corpus_tokens = [_tokenize(c.text) for c in chunks]
    sources = [c.source for c in chunks]
    bm25 = BM25Okapi(corpus_tokens) if corpus_tokens else None
    return bm25, sources


def clear_cache():
    _build_index.cache_clear()


def bm25_search(query_text: str, top_k: int = 20, data_dir=config.DATA_DIR) -> list[tuple[str, float]]:
    """Return [(source_filename, bm25_score), ...] sorted descending by
    score, for the top_k matches. Empty catalog -> empty list."""
    bm25, sources = _build_index(str(data_dir))
    if bm25 is None or not sources:
        return []

    query_tokens = _tokenize(query_text)
    if not query_tokens:
        return []

    scores = bm25.get_scores(query_tokens)
    ranked = sorted(zip(sources, scores), key=lambda pair: pair[1], reverse=True)
    return [(source, float(score)) for source, score in ranked[:top_k] if score > 0]