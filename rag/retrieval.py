"""
Hybrid retrieval: combines dense vector search (semantic/intent matching)
with BM25 sparse search (exact keyword/ID/column-name matching) using
Reciprocal Rank Fusion (RRF), then hands a wide candidate pool to the LLM
re-ranker in generate.py. This two-stage approach — cheap fusion retrieval
to cast a wide net, then an LLM (or a cross-encoder, if you swap it in) to
carefully re-order the top handful — tends to surface strong matches with
much higher confidence than dense search alone, especially when a query
uses different wording than the catalog ("how much customers paid" vs a
column literally named "sale_price").
"""

from __future__ import annotations

from . import config
from .bm25_search import bm25_search
from .vectorstore import query as dense_query, list_ingested_sources

RRF_K = 60  # standard RRF smoothing constant


def hybrid_query(query_text: str, pool_size: int = 20) -> list[dict]:
    """
    Returns up to pool_size candidate sources, ranked by fused dense+sparse
    score (descending), each as a dict with full catalog metadata plus:
        - dense_rank / sparse_rank (1-indexed, or None if absent from that list)
        - hybrid_score (RRF fused score, higher = better)
        - distance (kept for backward compatibility / display)
    """
    dense_hits = dense_query(query_text, top_k=pool_size)
    sparse_hits = bm25_search(query_text, top_k=pool_size)

    dense_rank = {hit["source"]: i + 1 for i, hit in enumerate(dense_hits)}
    sparse_rank = {source: i + 1 for i, (source, _score) in enumerate(sparse_hits)}

    # Metadata lookup for anything that only shows up via BM25 (dense_hits
    # already carries full metadata from Chroma).
    metadata_by_source = {hit["source"]: hit for hit in dense_hits}
    if set(sparse_rank) - set(metadata_by_source):
        for meta in list_ingested_sources():
            metadata_by_source.setdefault(meta.get("source"), {**meta, "text": "", "distance": 1.0})

    all_sources = set(dense_rank) | set(sparse_rank)

    fused = []
    for source in all_sources:
        d_rank = dense_rank.get(source)
        s_rank = sparse_rank.get(source)
        score = 0.0
        if d_rank is not None:
            score += 1.0 / (RRF_K + d_rank)
        if s_rank is not None:
            score += 1.0 / (RRF_K + s_rank)

        hit = dict(metadata_by_source.get(source, {"source": source}))
        hit["dense_rank"] = d_rank
        hit["sparse_rank"] = s_rank
        hit["hybrid_score"] = score
        fused.append(hit)

    fused.sort(key=lambda h: h["hybrid_score"], reverse=True)
    return fused[:pool_size]