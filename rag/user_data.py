"""
Turn a user's uploaded file into a candidate "data source" that competes
on equal footing with the catalog during retrieval — instead of only being
used as background context for the LLM.

We embed the uploaded file's column list with the SAME embedding model
used for the catalog, then compute cosine distance against the query,
matching Chroma's cosine-distance scale so the two can be merged and
sorted together into one ranked list.
"""

from __future__ import annotations

import math

from .vectorstore import _get_embedding_function

UPLOADED_SOURCE_ID = "USER-UPLOAD"


def _cosine_distance(vec_a: list[float], vec_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    cosine_similarity = dot / (norm_a * norm_b)
    return 1.0 - cosine_similarity


def build_uploaded_source_text(filename: str, columns: list[str]) -> str:
    """Text used both for embedding and as the context shown to the LLM."""
    return (
        f"Source: {filename} (Your Uploaded Data)\n"
        f"This is a dataset the user already has locally — already available, "
        f"no approval needed.\n"
        f"Fields: {', '.join(columns)}"
    )


def score_uploaded_file(query_text: str, filename: str, columns: list[str], n_rows: int, file_size_display: str) -> dict:
    """
    Returns a hit dict in the same shape as vectorstore.query() results, so
    it can be merged directly with catalog hits and ranked together.
    """
    doc_text = build_uploaded_source_text(filename, columns)

    embed_fn = _get_embedding_function()
    query_vec = embed_fn([query_text])[0]
    doc_vec = embed_fn([doc_text])[0]
    distance = _cosine_distance(query_vec, doc_vec)

    return {
        "text": doc_text,
        "distance": distance,
        "source": filename,
        "source_name": f"{filename} (Your Uploaded Data)",
        "source_id": UPLOADED_SOURCE_ID,
        "owner": "You",
        "approval_contact": "N/A — already in your possession",
        "access_level": "Already available locally — no approval needed",
        "update_frequency": "N/A",
        "format": f"Uploaded file ({n_rows} rows, {file_size_display})",
        "keywords": ", ".join(columns),
        "fields": ", ".join(columns),
        "is_uploaded": True,
    }
