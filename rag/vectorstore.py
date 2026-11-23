"""
Thin wrapper around ChromaDB + sentence-transformers for storing and
retrieving data-source catalog entries, including their structured
metadata (owner, approval contact, access level, keywords, fields).
"""

from __future__ import annotations

from functools import lru_cache

import chromadb
from chromadb.utils import embedding_functions

from . import config
from .loaders import Chunk

# Metadata keys we persist alongside each chunk in Chroma. Chroma metadata
# values must be scalars (str/int/float/bool), so list-like fields (fields,
# keywords) are stored as comma-joined strings by the loader already.
_METADATA_KEYS = [
    "source_name",
    "source_id",
    "owner",
    "approval_contact",
    "access_level",
    "update_frequency",
    "format",
    "keywords",
    "fields",
    "description",
    "field_types",
]


@lru_cache(maxsize=1)
def _get_embedding_function():
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=config.EMBEDDING_MODEL_NAME
    )


@lru_cache(maxsize=1)
def get_client() -> chromadb.ClientAPI:
    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.INDEX_DIR))


def get_collection():
    client = get_client()
    return client.get_or_create_collection(
        name=config.COLLECTION_NAME,
        embedding_function=_get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection():
    """Delete and recreate the collection (used before a fresh ingest)."""
    client = get_client()
    try:
        client.delete_collection(config.COLLECTION_NAME)
    except Exception:
        pass
    return get_collection()


def _build_metadata_dict(chunk: Chunk) -> dict:
    meta = {"source": chunk.source}
    for key in _METADATA_KEYS:
        value = chunk.metadata.get(key, "") if chunk.metadata else ""
        meta[key] = value if value else "unknown"
    return meta


def index_chunks(chunks: list[Chunk]) -> int:
    """Embed and store chunks (with their catalog metadata) in the vector
    store. Returns count indexed."""
    if not chunks:
        return 0

    collection = get_collection()
    collection.add(
        ids=[c.id for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[_build_metadata_dict(c) for c in chunks],
    )
    return len(chunks)


def query(question: str, top_k: int = config.TOP_K) -> list[dict]:
    """Return the top_k most relevant catalog entries for a query, each as
    a dict with the chunk text plus all catalog metadata fields."""
    collection = get_collection()
    if collection.count() == 0:
        return []

    results = collection.query(query_texts=[question], n_results=min(top_k, collection.count()))

    hits = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(docs, metas, dists):
        hit = {"text": doc, "distance": dist}
        hit.update(meta)  # source, source_name, owner, approval_contact, etc.
        hits.append(hit)

    return hits


def list_ingested_sources() -> list[dict]:
    """
    Return one entry per unique data source currently in the vector store,
    with its catalog metadata. Used to show the user what's actually been
    ingested, independent of any particular search query.
    """
    collection = get_collection()
    if collection.count() == 0:
        return []

    results = collection.get(include=["metadatas"])
    metadatas = results.get("metadatas", []) or []

    seen: dict[str, dict] = {}
    for meta in metadatas:
        key = meta.get("source", "unknown")
        if key not in seen:
            seen[key] = meta

    # Sort by source_id if present (SRC-001, SRC-002, ...), else by name.
    return sorted(seen.values(), key=lambda m: (m.get("source_id", ""), m.get("source_name", "")))


def collection_stats() -> dict:
    collection = get_collection()
    return {"count": collection.count()}