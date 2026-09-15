from unittest.mock import patch

import pytest

from fastapi.testclient import TestClient


@pytest.fixture
def session_module(monkeypatch):
    """Import app with a stubbed session and return the module for patching."""
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    import app

    return app


@pytest.fixture
def client(session_module):
    return TestClient(session_module.app)


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_index_serves_chat_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "FSSAI Regulation Assistant" in response.text


def test_chat_returns_answer_and_sources(client, session_module):
    with patch.object(session_module._session, "respond", return_value="A grounded answer.") as respond:
        with patch.object(session_module._session, "last_chunks", new=[]):
            response = client.post("/api/chat", json={"message": "Do I need a licence?"})

    respond.assert_called_once_with("Do I need a licence?")
    assert response.status_code == 200
    assert response.json()["answer"] == "A grounded answer."
    assert response.json()["sources"] == []


def test_chat_rejects_blank_message(client):
    response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 422