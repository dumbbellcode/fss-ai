#!/usr/bin/env python3
"""Export the local Chroma vector store into a Qdrant Cloud collection.

Run after ingesting regulations locally::

    uv run python -m retrieval.sync_to_qdrant \
        --qdrant-url https://<cluster>.qdrant.io \
        --qdrant-api-key <key> \
        --qdrant-collection fssai_regulations

The script creates the Qdrant collection with cosine distance when missing and
upserts every Chroma chunk (id, vector, text, metadata) into it. Running again
is idempotent: matching ids are overwritten, stale ids are left untouched.
"""

import argparse
import hashlib
import json

import chromadb

from ingestion.config import DEFAULT_CONFIG, IngestionConfig


def _chunk_id(text: str, metadata: dict) -> str:
    key = text + json.dumps(metadata, sort_keys=True)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _read_chroma(collection_name: str, persist_dir: str) -> tuple[list[str], list[list], list[str], list[dict]]:
    client = chromadb.PersistentClient(path=persist_dir)
    collection = client.get_collection(collection_name)
    fetched = collection.get(include=["documents", "metadatas", "embeddings"])
    ids = fetched["ids"]
    return ids, fetched["embeddings"], fetched["documents"], fetched["metadatas"]


def sync_to_qdrant(
    collection_name: str,
    persist_dir: str,
    qdrant_url: str,
    qdrant_api_key: str,
    qdrant_collection: str,
) -> int:
    """Copy the local Chroma ``collection_name`` into ``qdrant_collection``.

    Returns the number of points upserted.
    """
    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    ids, embeddings, documents, metadatas = _read_chroma(collection_name, persist_dir)
    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    existing = client.collection_exists(qdrant_collection)
    if not existing:
        vector_size = len(embeddings[0]) if embeddings else 0
        if vector_size == 0:
            raise ValueError("collection is empty; nothing to sync")
        client.create_collection(
            collection_name=qdrant_collection,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )

    points = [
        models.PointStruct(
            id=int(_chunk_id(text, metadata), 16) % (2**63),
            vector=vector,
            payload={"text": text, **metadata},
        )
        for text, vector, metadata in zip(documents, embeddings, metadatas)
        if text is not None
    ]
    if points:
        client.upsert(collection_name=qdrant_collection, points=points)
    return len(points)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync the local Chroma store into Qdrant Cloud.")
    parser.add_argument("--collection", default=DEFAULT_CONFIG.collection_name)
    parser.add_argument("--persist-dir", default=DEFAULT_CONFIG.persist_dir)
    parser.add_argument("--qdrant-url", required=True)
    parser.add_argument("--qdrant-api-key", required=True)
    parser.add_argument("--qdrant-collection", default=DEFAULT_CONFIG.collection_name)
    args = parser.parse_args()

    count = sync_to_qdrant(
        collection_name=args.collection,
        persist_dir=args.persist_dir,
        qdrant_url=args.qdrant_url,
        qdrant_api_key=args.qdrant_api_key,
        qdrant_collection=args.qdrant_collection,
    )
    print(f"Upserted {count} points into Qdrant collection '{args.qdrant_collection}'")


if __name__ == "__main__":
    main()