from unittest.mock import Mock, patch

import pytest

from retrieval.retrieve import RetrievedChunk, retrieve
from retrieval.vectorstores import VectorHit


def _store():
    store = Mock()
    store.query.return_value = [
        VectorHit(text="first document", metadata={"section": "1.1"}, distance=0.1),
        VectorHit(text="second document", metadata={"section": "1.2"}, distance=0.4),
    ]
    return store


def test_retrieve_embeds_question_and_returns_ranked_chunks():
    embedder = Mock()
    embedder.embed_query.return_value = [0.2, 0.3]

    with patch("retrieval.retrieve.build_vector_store", return_value=_store()) as store_builder:
        with patch("retrieval.retrieve.build_embeddings", return_value=embedder):
            results = retrieve("What is the registration requirement?", top_k=2)

    assert results == [
        RetrievedChunk("first document", {"section": "1.1"}, 0.1),
        RetrievedChunk("second document", {"section": "1.2"}, 0.4),
    ]
    embedder.embed_query.assert_called_once_with("What is the registration requirement?")
    store_builder.assert_called_once()
    store_builder.return_value.query.assert_called_once_with([0.2, 0.3], top_k=2, where=None)


def test_retrieve_passes_metadata_filter():
    embedder = Mock()
    embedder.embed_query.return_value = [0.2]

    with patch("retrieval.retrieve.build_vector_store", return_value=_store()) as store_builder:
        with patch("retrieval.retrieve.build_embeddings", return_value=embedder):
            retrieve("question", where={"chapter": 2})

    assert store_builder.return_value.query.call_args.kwargs["where"] == {"chapter": 2}


def test_retrieve_uses_qdrant_backend_when_configured():
    embedder = Mock()
    embedder.embed_query.return_value = [0.1, 0.2, 0.3]

    store = _store()
    with patch("retrieval.retrieve.build_vector_store", return_value=store) as store_builder:
        with patch("retrieval.retrieve.build_embeddings", return_value=embedder):
            results = retrieve(
                "question",
                backend="qdrant",
                qdrant_url="https://example.qdrant.io",
                qdrant_api_key="secret",
                top_k=3,
            )

    store_builder.assert_called_once_with(
        backend="qdrant",
        collection_name="fssai_regulations",
        persist_dir="db",
        qdrant_url="https://example.qdrant.io",
        qdrant_api_key="secret",
    )
    store.query.assert_called_once_with([0.1, 0.2, 0.3], top_k=3, where=None)
    assert results == [
        RetrievedChunk("first document", {"section": "1.1"}, 0.1),
        RetrievedChunk("second document", {"section": "1.2"}, 0.4),
    ]


@pytest.mark.parametrize("question", ["", "   "])
def test_retrieve_rejects_empty_question(question):
    with pytest.raises(ValueError, match="question must not be empty"):
        retrieve(question)


def test_retrieve_rejects_invalid_top_k():
    with pytest.raises(ValueError, match="top_k must be at least 1"):
        retrieve("question", top_k=0)