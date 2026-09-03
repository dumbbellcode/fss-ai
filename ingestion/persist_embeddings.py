#!/usr/bin/env python3
"""Persist chunks and their embeddings into a Chroma vector store."""

import argparse
import hashlib
import json
from pathlib import Path

import chromadb

from ingestion.chunks_creator import Chunk, create_chunks
from ingestion.config import CHUNK_OVERLAP_TOKENS, CHUNK_SIZE_TOKENS, COLLECTION_NAME, EMBEDDING_MODEL, PERSIST_DIR
from ingestion.create_embeddings import create_embeddings
from pre_processing.regulation_parser import Regulation

DEFAULT_COLLECTION = COLLECTION_NAME
DEFAULT_PERSIST_DIR = PERSIST_DIR


def _chunk_id(chunk: Chunk) -> str:
    key = chunk.text + json.dumps(chunk.metadata.model_dump(mode="json", exclude_none=True), sort_keys=True)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def persist_embeddings(
    chunks: list[Chunk],
    embeddings: list[list[float]],
    collection_name: str = DEFAULT_COLLECTION,
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
) -> int:
    """Upsert ``chunks`` with ``embeddings`` into a Chroma collection.

    Returns the number of documents in the collection after the upsert. Chunk
    ids are deterministic hashes of (text, metadata) so re-running is idempotent.
    """
    client = chromadb.PersistentClient(path=str(persist_dir))
    collection = client.get_or_create_collection(collection_name)
    if not chunks:
        return collection.count()

    # Replacing this regulation's records removes stale chunks after changing
    # chunk size, overlap, or the source regulation while preserving others.
    collection.delete(where={"regulation": chunks[0].metadata.regulation})
    collection.add(
        ids=[_chunk_id(chunk) for chunk in chunks],
        documents=[chunk.text for chunk in chunks],
        metadatas=[chunk.metadata.model_dump(mode="json", exclude_none=True) for chunk in chunks],
        embeddings=[list(vector) for vector in embeddings],
    )
    return collection.count()


def ingest_regulation(
    regulation_json_path: str | Path,
    collection_name: str = DEFAULT_COLLECTION,
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    model: str | None = None,
    chunk_size_tokens: int = CHUNK_SIZE_TOKENS,
    chunk_overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> int:
    """Chunk a regulation JSON, embed the chunks, and persist them to Chroma.

    ``model``, ``chunk_size_tokens`` and ``chunk_overlap_tokens`` override the
    defaults, so a benchmark can ingest the same regulation into separate
    ``collection_name``s and compare retrieval accuracy across configurations.
    """
    path = Path(regulation_json_path)
    regulation = Regulation.model_validate_json(path.read_text(encoding="utf-8"))
    chunks = create_chunks(
        regulation,
        chunk_size_tokens=chunk_size_tokens,
        chunk_overlap_tokens=chunk_overlap_tokens,
    )
    embeddings = create_embeddings(chunks, model=model or EMBEDDING_MODEL)
    count = persist_embeddings(chunks, embeddings, collection_name=collection_name, persist_dir=persist_dir)
    print(f"Persisted {count} documents to collection '{collection_name}' in '{persist_dir}'")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk, embed, and persist a regulation JSON into Chroma.")
    parser.add_argument("regulation_json_path", type=Path)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--persist-dir", default=DEFAULT_PERSIST_DIR)
    parser.add_argument("--model", default=None, help="Embedding model id (OpenRouter format).")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE_TOKENS, help="Chunk size in tokens.")
    parser.add_argument("--chunk-overlap", type=int, default=CHUNK_OVERLAP_TOKENS, help="Chunk overlap in tokens.")
    args = parser.parse_args()

    ingest_regulation(
        args.regulation_json_path,
        collection_name=args.collection,
        persist_dir=args.persist_dir,
        model=args.model,
        chunk_size_tokens=args.chunk_size,
        chunk_overlap_tokens=args.chunk_overlap,
    )


if __name__ == "__main__":
    main()
