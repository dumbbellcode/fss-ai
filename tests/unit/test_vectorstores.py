from unittest.mock import Mock, patch

import pytest

from retrieval.vectorstores import (
    ChromaVectorStore,
    QdrantVectorStore,
    VectorHit,
    _to_qdrant_filter,
    build_vector_store,
)


def test_chroma_store_maps_query_result_to_hits():
    collection = Mock()
    collection.query.return_value = {
        "documents": [["doc"]],
        "metadatas": [[{"section": "1.1"}]],
        "distances": [[0.05]],
    }
    with patch("chromadb.PersistentClient") as client_cls:
        client_cls.return_value.get_collection.return_value = collection
        store = ChromaVectorStore(collection_name="col", persist_dir="db")

    hits = store.query([0.1, 0.2], top_k=1, where={"regulation": "R"})

    assert hits == [VectorHit(text="doc", metadata={"section": "1.1"}, distance=0.05)]
    assert collection.query.call_args.kwargs["where"] == {"regulation": "R"}


def test_qdrant_store_converts_cosine_score_to_distance():
    point = Mock()
    point.score = 0.8
    point.payload = {"text": "qdrant doc", "section": "2.2", "regulation": "R"}
    query_result = Mock()
    query_result.points = [point]
    client = Mock()
    client.query_points.return_value = query_result

    with patch("qdrant_client.QdrantClient", return_value=client):
        store = QdrantVectorStore(collection_name="col", url="http://localhost:6333", api_key="k")

    hits = store.query([0.5, 0.5], top_k=1, where=None)

    assert len(hits) == 1
    assert hits[0].text == "qdrant doc"
    assert hits[0].metadata == {"section": "2.2", "regulation": "R"}
    assert hits[0].distance == pytest.approx(0.2)


def test_qdrant_store_passes_filter_through():
    point = Mock()
    point.score = 0.9
    point.payload = {"text": "doc", "chapter": 1}
    query_result = Mock()
    query_result.points = [point]
    client = Mock()
    client.query_points.return_value = query_result

    with patch("qdrant_client.QdrantClient", return_value=client):
        store = QdrantVectorStore(collection_name="col", url="http://localhost:6333", api_key="k")

    store.query([0.5], top_k=1, where={"chapter": 1})

    assert client.query_points.call_args.kwargs["query_filter"].must[0].key == "chapter"


def test_to_qdrant_filter_basic_and_or():
    from qdrant_client.http import models

    result = _to_qdrant_filter({"regulation": "R", "$or": [{"chapter": 1}, {"chapter": 2}]})

    assert isinstance(result, models.Filter)
    assert len(result.must) == 2


def test_build_vector_store_unknown_backend_rejected():
    with pytest.raises(ValueError, match="unknown vector store backend"):
        build_vector_store(backend="pinecone", collection_name="c", persist_dir="db")


def test_build_vector_store_qdrant_requires_url():
    with pytest.raises(ValueError, match="qdrant_url"):
        build_vector_store(backend="qdrant", collection_name="c")


def test_build_vector_store_returns_qdrant_store():
    with patch("qdrant_client.QdrantClient"):
        store = build_vector_store(
            backend="qdrant",
            collection_name="col",
            qdrant_url="http://localhost:6333",
        )
    assert isinstance(store, QdrantVectorStore)