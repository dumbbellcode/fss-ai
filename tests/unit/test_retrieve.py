from unittest.mock import Mock, patch

import pytest

from retrieval.retrieve import RetrievedChunk, retrieve


def _collection():
    collection = Mock()
    collection.query.return_value = {
        "documents": [["first document", "second document"]],
        "metadatas": [[{"section": "1.1"}, {"section": "1.2"}]],
        "distances": [[0.1, 0.4]],
    }
    return collection


def test_retrieve_embeds_question_and_returns_ranked_chunks():
    collection = _collection()
    embedder = Mock()
    embedder.embed_query.return_value = [0.2, 0.3]

    with patch("retrieval.retrieve.chromadb.PersistentClient") as client_cls:
        client_cls.return_value.get_collection.return_value = collection
        with patch("retrieval.retrieve.build_embeddings", return_value=embedder):
            results = retrieve("What is the registration requirement?", top_k=2)

    assert results == [
        RetrievedChunk("first document", {"section": "1.1"}, 0.1),
        RetrievedChunk("second document", {"section": "1.2"}, 0.4),
    ]
    embedder.embed_query.assert_called_once_with("What is the registration requirement?")
    collection.query.assert_called_once_with(
        query_embeddings=[[0.2, 0.3]],
        n_results=2,
        include=["documents", "metadatas", "distances"],
    )


def test_retrieve_passes_metadata_filter():
    collection = _collection()
    embedder = Mock()
    embedder.embed_query.return_value = [0.2]

    with patch("retrieval.retrieve.chromadb.PersistentClient") as client_cls:
        client_cls.return_value.get_collection.return_value = collection
        with patch("retrieval.retrieve.build_embeddings", return_value=embedder):
            retrieve("question", where={"chapter": 2})

    assert collection.query.call_args.kwargs["where"] == {"chapter": 2}


@pytest.mark.parametrize("question", ["", "   "])
def test_retrieve_rejects_empty_question(question):
    with pytest.raises(ValueError, match="question must not be empty"):
        retrieve(question)


def test_retrieve_rejects_invalid_top_k():
    with pytest.raises(ValueError, match="top_k must be at least 1"):
        retrieve("question", top_k=0)
