import chromadb
import pytest

from ingestion.chunks_creator import Chunk
from ingestion.create_embeddings import create_embeddings
from ingestion.persist_embeddings import persist_embeddings

pytestmark = pytest.mark.integration

CHUNKS = [
    Chunk(text="hello world", metadata={"regulation": "x", "chapter": 1}),
    Chunk(text="another test document about food safety", metadata={"regulation": "x", "chapter": 1}),
]


def test_embed_and_persist_roundtrip(tmp_path):
    embeddings = create_embeddings(CHUNKS)
    assert len(embeddings) == len(CHUNKS)
    assert len(embeddings[0]) > 0

    count = persist_embeddings(CHUNKS, embeddings, collection_name="test_coll", persist_dir=tmp_path)
    assert count == len(CHUNKS)

    client = chromadb.PersistentClient(path=str(tmp_path))
    collection = client.get_collection("test_coll")
    assert collection.count() == len(CHUNKS)
    got = collection.get(include=["documents", "metadatas"])
    assert got["documents"] == [chunk.text for chunk in CHUNKS]


def test_persist_is_idempotent(tmp_path):
    embeddings = create_embeddings(CHUNKS)
    persist_embeddings(CHUNKS, embeddings, collection_name="idem_coll", persist_dir=tmp_path)
    persist_embeddings(CHUNKS, embeddings, collection_name="idem_coll", persist_dir=tmp_path)

    client = chromadb.PersistentClient(path=str(tmp_path))
    assert client.get_collection("idem_coll").count() == len(CHUNKS)