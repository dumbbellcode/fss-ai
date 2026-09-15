from unittest.mock import Mock, patch

import pytest

from retrieval.chat import ChatConfig, ChatMessage, ChatSession, format_passages, respond
from retrieval.retrieve import RetrievedChunk


def _chunk(text: str, metadata: dict | None = None, distance: float = 0.1) -> RetrievedChunk:
    return RetrievedChunk(text=text, metadata={"regulation": "Regulation 1", **(metadata or {})}, distance=distance)


def test_format_passages_includes_source_location():
    chunks = [
        _chunk("Food business operator duties", {"chapter": 2, "section": "2.1"}),
        _chunk("Licence form text", {"schedule": "Schedule 1", "form": "Form A"}),
    ]
    passages = format_passages(chunks)

    assert "Regulation: Regulation 1, chapter 2, section 2.1" in passages
    assert "[1]" in passages and "[2]" in passages
    assert "Food business operator duties" in passages
    assert "Licence form text" in passages


def test_respond_retrieves_then_answers_and_records_history():
    session = ChatSession()
    llm = Mock()
    llm.invoke.return_value.content = "A grounded answer with a citation."
    chunks = [_chunk("Duties text", {"chapter": 1, "section": "1.2"}, 0.05)]

    with patch("retrieval.chat.retrieve", return_value=chunks) as retrieval:
        with patch("retrieval.chat.ChatOpenAI", return_value=llm):
            answer = session.respond("What are the duties of a food business operator?")

    retrieval.assert_called_once()
    assert answer == "A grounded answer with a citation."
    assert session.history == [
        ChatMessage(role="user", content="What are the duties of a food business operator?"),
        ChatMessage(role="assistant", content="A grounded answer with a citation."),
    ]
    assert session.last_chunks == chunks


def test_respond_passes_retrieval_options():
    session = ChatSession(
        chat_config=ChatConfig(top_k=3),
        collection_name="custom",
        persist_dir="/tmp/db",
        embedding_model="openai/text-embedding-3-small",
        where={"regulation": "Regulation 1"},
    )
    llm = Mock()
    llm.invoke.return_value.content = "Answer."
    with patch("retrieval.chat.retrieve", return_value=[_chunk("text")]) as retrieval:
        with patch("retrieval.chat.ChatOpenAI", return_value=llm):
            session.respond("question")

    kwargs = retrieval.call_args.kwargs
    assert kwargs["collection_name"] == "custom"
    assert kwargs["persist_dir"] == "/tmp/db"
    assert kwargs["model"] == "openai/text-embedding-3-small"
    assert kwargs["top_k"] == 3
    assert kwargs["where"] == {"regulation": "Regulation 1"}


def test_respond_answers_without_passages_when_retrieval_is_empty():
    session = ChatSession()

    with patch("retrieval.chat.retrieve", return_value=[]):
        answer = session.respond("obscure question")

    assert "could not find any matching passages" in answer
    assert session.history[-1].role == "assistant"


def test_respond_rejects_blank_message():
    session = ChatSession()
    with pytest.raises(ValueError, match="message must not be empty"):
        session.respond("   ")


def test_reset_clears_history_and_sources():
    session = ChatSession()
    llm = Mock()
    llm.invoke.return_value.content = "Answer."
    with patch("retrieval.chat.retrieve", return_value=[_chunk("text")]):
        with patch("retrieval.chat.ChatOpenAI", return_value=llm):
            session.respond("question")

    session.reset()

    assert session.history == []
    assert session.last_chunks == []


def test_stateless_respond_replays_history():
    llm = Mock()
    llm.invoke.return_value.content = "Follow-up answer."
    chunks = [_chunk("text")]

    with patch("retrieval.chat.retrieve", return_value=chunks):
        with patch("retrieval.chat.ChatOpenAI", return_value=llm):
            answer = respond(
                "And the fees?",
                [["What is a licence?", "A licence is a permit."]],
            )

    assert answer == "Follow-up answer."
    prompt = llm.invoke.call_args.args[0][0].content
    assert "What is a licence?" in prompt
    assert "A licence is a permit." in prompt