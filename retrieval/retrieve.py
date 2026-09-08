#!/usr/bin/env python3
"""Retrieve regulation chunks for a single natural-language question."""

import argparse
from dataclasses import dataclass
from pathlib import Path

import chromadb

from ingestion.config import DEFAULT_CONFIG, IngestionConfig
from ingestion.create_embeddings import build_embeddings


@dataclass(frozen=True)
class RetrievedChunk:
    """A retrieved document and its source metadata.

    Chroma distances are lower for more similar results.
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
) -> list[RetrievedChunk]:
    """Retrieve the most similar indexed chunks for ``question``."""
    if not question.strip():
        raise ValueError("question must not be empty")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    collection_name = collection_name or config.collection_name
    persist_dir = persist_dir or config.persist_dir
    client = chromadb.PersistentClient(path=str(persist_dir))
    collection = client.get_collection(collection_name)
    query_embedding = build_embeddings(model=model, config=config).embed_query(question)

    query_args = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where is not None:
        query_args["where"] = where
    result = collection.query(**query_args)

    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]
    return [
        RetrievedChunk(text=text, metadata=metadata, distance=distance)
        for text, metadata, distance in zip(documents, metadatas, distances)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve regulation chunks for a question.")
    parser.add_argument("question")
    parser.add_argument("--collection", default=DEFAULT_CONFIG.collection_name)
    parser.add_argument("--persist-dir", default=DEFAULT_CONFIG.persist_dir)
    parser.add_argument("--model", default=DEFAULT_CONFIG.embedding_model)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    results = retrieve(
        args.question,
        collection_name=args.collection,
        persist_dir=args.persist_dir,
        model=args.model,
        top_k=args.top_k,
    )
    for index, result in enumerate(results, start=1):
        print(f"\n[{index}] distance={result.distance:.4f}")
        print(f"metadata={result.metadata}")
        print(result.text)


if __name__ == "__main__":
    main()
