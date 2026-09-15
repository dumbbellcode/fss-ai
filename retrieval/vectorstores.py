#!/usr/bin/env python3
"""Pluggable vector stores behind retrieval.

Chromabase Chroma remains the default (used in local dev/tests/evals). A
Qdrant backend is provided for the hosted chat product so the vector store
lives in Qdrant Cloud instead of the app's ephemeral disk.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

BackendName = Literal["chroma", "qdrant"]


@dataclass(frozen=True)
class VectorHit:
    """One retrieved item from a vector store, before mapping into app types."""

    text: str
    metadata: dict
    distance: float  # lower is more similar (Qdrant cosine score converted)


class VectorStore(Protocol):
    """Query contract implemented by each backend."""

    def query(self, embedding: list[float], top_k: int, where: dict | None = None) -> list[VectorHit]:
        ...


def _normalize_where(where: dict | None) -> dict | None:
    """Accept ``where`` filters in the Chroma form used by callers today."""
    if not where:
        return None
    return where


class ChromaVectorStore:
    """Chroma persistence backend (the local default)."""

    def __init__(self, collection_name: str, persist_dir: str | Path) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_collection(collection_name)

    def query(self, embedding: list[float], top_k: int, where: dict | None = None) -> list[VectorHit]:
        query_args = {
            "query_embeddings": [embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        where = _normalize_where(where)
        if where is not None:
            query_args["where"] = where
        result = self._collection.query(**query_args)

        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]
        return [
            VectorHit(text=text, metadata=metadata, distance=distance)
            for text, metadata, distance in zip(documents, metadatas, distances)
        ]


def _to_qdrant_filter(where: dict | None):
    """Convert a Chroma-style ``where`` dict into a Qdrant payload filter."""
    from qdrant_client.http import models

    if not where:
        return None
    must: list = []
    should: list = []
    for key, value in where.items():
        if key == "$and" and isinstance(value, list):
            for clause in value:
                nested = _to_qdrant_filter(clause)
                if nested is not None:
                    must.append(nested)
        elif key == "$or" and isinstance(value, list):
            for clause in value:
                nested = _to_qdrant_filter(clause)
                if nested is not None:
                    should.append(models.Filter(must=[nested]))
        elif isinstance(value, dict) and "$in" in value and isinstance(value["$in"], list):
            must.append(models.FieldCondition(key=key, match=models.MatchAny(any=value["$in"])))
        else:
            must.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    if should:
        must.append(models.Filter(should=should))
    if not must:
        return None
    return models.Filter(must=must)


class QdrantVectorStore:
    """Qdrant Cloud backend for the hosted chat product."""

    def __init__(
        self,
        collection_name: str,
        url: str,
        api_key: str | None = None,
    ) -> None:
        from qdrant_client import QdrantClient

        self._client = QdrantClient(url=url, api_key=api_key)
        self._collection = collection_name

    def query(self, embedding: list[float], top_k: int, where: dict | None = None) -> list[VectorHit]:
        from qdrant_client.http import models

        result = self._client.query_points(
            collection_name=self._collection,
            query=embedding,
            limit=top_k,
            query_filter=_to_qdrant_filter(where) or models.Filter(must=[]),
            with_payload=True,
        )
        hits: list[VectorHit] = []
        for point in result.points:
            payload = point.payload or {}
            text = payload.get("text", "")
            metadata = {key: value for key, value in payload.items() if key != "text"}
            # Qdrant returns cosine similarity (higher = more similar); convert so
            # distance (lower = more similar) stays consistent with Chroma.
            hits.append(VectorHit(text=text, metadata=metadata, distance=1.0 - point.score))
        return hits


def build_vector_store(
    backend: BackendName = "chroma",
    collection_name: str | None = None,
    persist_dir: str | Path | None = None,
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
) -> VectorStore:
    """Build the configured vector-store backend."""
    if backend == "chroma":
        if persist_dir is None:
            raise ValueError("persist_dir is required for the chroma backend")
        if collection_name is None:
            raise ValueError("collection_name is required for the chroma backend")
        return ChromaVectorStore(collection_name=collection_name, persist_dir=persist_dir)
    if backend == "qdrant":
        if qdrant_url is None:
            raise ValueError("qdrant_url is required for the qdrant backend")
        if collection_name is None:
            raise ValueError("collection_name is required for the qdrant backend")
        return QdrantVectorStore(collection_name=collection_name, url=qdrant_url, api_key=qdrant_api_key)
    raise ValueError(f"unknown vector store backend: {backend!r}")