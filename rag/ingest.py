"""
Build (or rebuild) the vector index from every data-source catalog entry
in data/catalog/.

Usage:
    python -m rag.ingest              # incremental add
    python -m rag.ingest --rebuild    # wipe and rebuild from scratch
"""

from __future__ import annotations

import argparse
import sys

from . import config
from .loaders import build_chunks
from .vectorstore import index_chunks, reset_collection, collection_stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the data-source catalog into the vector store.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete the existing index and rebuild it from scratch.",
    )
    args = parser.parse_args()

    if not config.DATA_DIR.exists() or not any(config.DATA_DIR.iterdir()):
        print(f"No catalog entries found in {config.DATA_DIR}. Add .xlsx workbooks there first.")
        sys.exit(1)

    if args.rebuild:
        print("Rebuilding index from scratch...")
        reset_collection()

    print("Loading catalog entries and extracting metadata...")
    chunks = build_chunks()
    print(f"  -> {len(chunks)} chunks from files in {config.DATA_DIR}")

    if not chunks:
        print("No content to index. Check that your catalog files aren't empty.")
        sys.exit(1)

    print("Embedding and storing chunks (first run downloads the embedding model)...")
    count = index_chunks(chunks)
    print(f"Indexed {count} chunks.")

    stats = collection_stats()
    print(f"Vector store now contains {stats['count']} chunks total.")


if __name__ == "__main__":
    main()