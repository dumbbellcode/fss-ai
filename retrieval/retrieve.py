#!/usr/bin/env python3
"""Retrieve regulation chunks for a single natural-language question."""

import argparse
from dataclasses import dataclass
from pathlib import Path

from ingestion.config import DEFAULT_CONFIG, IngestionConfig
from ingestion.create_embeddings import build_embeddings
from retrieval.vectorstores import BackendName, build_vector_store


@dataclass(frozen=True)
class RetrievedChunk:
    """A retrieved document and its source metadata.

    ``distance`` is a similarity distance: lower means more similar. For the
    Qdrant backend the cosine score is converted (``1 - score``) to keep this
    semantics consistent across backends.
    """

    text: str
    metadata: dict
    distance: float


def retrieve(
    question: str,
    collection_name: str | None = None,
    persist_dir: str | Path | None = None,
    model: str | None = None,
    top_k: int = 5,
    where: dict | None = None,
    config: IngestionConfig = DEFAULT_CONFIG,
    backend: BackendName = "chroma",
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
    qdrant_collection: str | None = None,
) -> list[RetrievedChunk]:
    """Retrieve the most similar indexed chunks for ``question``."""
    if not question.strip():
        raise ValueError("question must not be empty")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    collection_name = collection_name or qdrant_collection or config.collection_name
    persist_dir = persist_dir or config.persist_dir
    store = build_vector_store(
        backend=backend,
        collection_name=collection_name,
        persist_dir=persist_dir,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
    )
    query_embedding = build_embeddings(model=model, config=config).embed_query(question)

    hits = store.query(query_embedding, top_k=top_k, where=where)
    return [
        RetrievedChunk(text=hit.text, metadata=hit.metadata, distance=hit.distance)
        for hit in hits
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve regulation chunks for a question.")
    parser.add_argument("question")
    parser.add_argument("--collection", default=DEFAULT_CONFIG.collection_name)
    parser.add_argument("--persist-dir", default=DEFAULT_CONFIG.persist_dir)
    parser.add_argument("--model", default=DEFAULT_CONFIG.embedding_model)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--backend", choices=("chroma", "qdrant"), default="chroma")
    parser.add_argument("--qdrant-url", help="Qdrant endpoint URL (qdrant backend).")
    parser.add_argument("--qdrant-api-key", help="Qdrant API key (qdrant backend).")
    args = parser.parse_args()

    results = retrieve(
        args.question,
        collection_name=args.collection,
        persist_dir=args.persist_dir,
        model=args.model,
        top_k=args.top_k,
        backend=args.backend,
        qdrant_url=args.qdrant_url,
        qdrant_api_key=args.qdrant_api_key,
    )
    for index, result in enumerate(results, start=1):
        print(f"\n[{index}] distance={result.distance:.4f}")
        print(f"metadata={result.metadata}")
        print(result.text)


if __name__ == "__main__":
    main()
