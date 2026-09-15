#!/usr/bin/env python3
"""Minimal chat abstraction over retrieval for a chat UI.

The public surface mirrors the simplest chat interfaces (e.g. Gradio's
``gr.ChatInterface``): a stateless ``respond(message, history)`` callable that a
UI can bind directly, plus a stateful :class:`ChatSession` that owns the
conversation and the answered question re-retrieves its evidence.

Example UI wiring (dependency-light, no framework needed)::

    from retrieval.chat import respond

    # Gradio:
    # import gradio as gr
    # gr.ChatInterface(respond).launch()

    # Or any UI that shows the last answer plus sources:
    # session = ChatSession(); print(session.respond("What is a food business?"))
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ingestion.config import DEFAULT_CONFIG as DEFAULT_INGESTION_CONFIG, IngestionConfig
from retrieval.retrieve import RetrievedChunk, retrieve

load_dotenv()

DEFAULT_SYSTEM_PROMPT = """You are a helpful assistant that answers questions about FSSAI (Food Safety and Standards Authority of India) regulations.
Answer using only the retrieved passages provided below. If the passages do not contain the answer, say that you could not find it in the available regulatory text instead of guessing.
When you can, cite the regulation chapter/section the answer comes from."""


@dataclass(frozen=True)
class ChatConfig:
    """Settings for LLM answer generation in a chat session."""

    model: str = "deepseek/deepseek-v4-flash"
    base_url: str = "https://openrouter.ai/api/v1"
    api_key_env: str = "OPENROUTER_API_KEY"
    temperature: float = 0.0
    max_tokens: int = 1_024
    top_k: int = 5
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_history_messages: int = 10


DEFAULT_CHAT_CONFIG = ChatConfig()


@dataclass
class ChatMessage:
    """One turn in a conversation."""

    role: Literal["user", "assistant"]
    content: str


def _format_location(metadata: dict) -> str:
    """Render the source location fields of a chunk's metadata."""
    parts = []
    for key in ("chapter", "section", "subsection", "schedule", "annexure", "form"):
        value = metadata.get(key)
        if value is not None:
            parts.append(f"{key} {value}")
    regulation = metadata.get("regulation")
    if regulation:
        parts.insert(0, f"Regulation: {regulation}")
    return ", ".join(parts) if parts else "unknown source"


def format_passages(chunks: Iterable[RetrievedChunk]) -> str:
    """Format retrieved chunks as a numbered passage list for the LLM prompt."""
    passages = []
    for index, chunk in enumerate(chunks, start=1):
        passages.append(
            f"[{index}] Source: {_format_location(chunk.metadata)}\n{chunk.text.strip()}"
        )
    return "\n\n".join(passages)


def _format_history(messages: list[ChatMessage]) -> str:
    """Render recent turns as plain text for conversational context."""
    lines = []
    for message in messages:
        speaker = "User" if message.role == "user" else "Assistant"
        lines.append(f"{speaker}: {message.content}")
    return "\n".join(lines)


class ChatSession:
    """A single conversation backed by vector retrieval plus LLM answering.

    ``respond`` appends the user message to ``history``, retrieves the most
    relevant regulation chunks, generates an answer grounded in them, appends
    the assistant turn, and returns the answer text. The evidence used for the
    last answer is available via :attr:`last_chunks` so a UI can show sources.
    """

    def __init__(
        self,
        chat_config: ChatConfig = DEFAULT_CHAT_CONFIG,
        ingestion_config: IngestionConfig = DEFAULT_INGESTION_CONFIG,
        collection_name: str | None = None,
        persist_dir: str | Path | None = None,
        embedding_model: str | None = None,
        where: dict | None = None,
        backend: str = "chroma",
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
    ) -> None:
        self.chat_config = chat_config
        self.ingestion_config = ingestion_config
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self.embedding_model = embedding_model
        self.where = where
        self.backend = backend
        self.qdrant_url = qdrant_url
        self.qdrant_api_key = qdrant_api_key
        self.history: list[ChatMessage] = []
        self.last_chunks: list[RetrievedChunk] = []

    def reset(self) -> None:
        """Clear the conversation history and last evidence."""
        self.history.clear()
        self.last_chunks.clear()

    def _recent_history(self) -> list[ChatMessage]:
        return self.history[-self.chat_config.max_history_messages :]

    def _answer(self, question: str) -> str:
        """Call the LLM with the question, history, and retrieved passages."""
        passages = format_passages(self.last_chunks)
        history = _format_history(self._recent_history())
        llm = ChatOpenAI(
            model=self.chat_config.model,
            base_url=self.chat_config.base_url,
            api_key=os.environ[self.chat_config.api_key_env],
            temperature=self.chat_config.temperature,
            max_tokens=self.chat_config.max_tokens,
        )
        prompt = (
            f"{self.chat_config.system_prompt}\n\n"
            f"Conversation so far:\n{history}\n\n"
            f"Retrieved passages:\n{passages}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )
        response = llm.invoke([SystemMessage(content=prompt), HumanMessage(content=question)])
        return response.content if isinstance(response.content, str) else str(response.content)

    def respond(self, message: str) -> str:
        """Process one user ``message`` and return the assistant answer."""
        message = message.strip()
        if not message:
            raise ValueError("message must not be empty")
        self.history.append(ChatMessage(role="user", content=message))
        self.last_chunks = retrieve(
            message,
            collection_name=self.collection_name,
            persist_dir=self.persist_dir,
            model=self.embedding_model,
            top_k=self.chat_config.top_k,
            where=self.where,
            config=self.ingestion_config,
            backend=self.backend,
            qdrant_url=self.qdrant_url,
            qdrant_api_key=self.qdrant_api_key,
        )
        if not self.last_chunks:
            answer = (
                "I could not find any matching passages in the indexed regulations "
                "to answer that question."
            )
        else:
            answer = self._answer(message)
        self.history.append(ChatMessage(role="assistant", content=answer))
        return answer


def respond(message: str, history: list[list[str] | tuple[str, str]]) -> str:
    """Stateless handler matching the ``gr.ChatInterface`` fn signature.

    ``history`` is the UI's ``[[user, assistant], ...]`` turns; each call
    replays it into a fresh session so the returned string is only the new
    assistant answer.
    """
    session = ChatSession()
    for user, assistant in history:
        session.history.append(ChatMessage(role="user", content=user))
        session.history.append(ChatMessage(role="assistant", content=assistant))
    return session.respond(message)


def main() -> None:
    """Repl-style chat loop for trying the abstraction without a UI."""
    import argparse

    parser = argparse.ArgumentParser(description="Ask questions against the indexed regulations in a chat loop.")
    parser.add_argument("--collection", default=DEFAULT_INGESTION_CONFIG.collection_name)
    parser.add_argument("--persist-dir", default=DEFAULT_INGESTION_CONFIG.persist_dir)
    parser.add_argument("--top-k", type=int, default=DEFAULT_CHAT_CONFIG.top_k)
    args = parser.parse_args()

    session = ChatSession(
        chat_config=ChatConfig(top_k=args.top_k),
        collection_name=args.collection,
        persist_dir=args.persist_dir,
    )
    print("Chat ready. Type your questions; Ctrl-D to exit.")
    try:
        while True:
            question = input("> ").strip()
            if not question:
                continue
            print(session.respond(question))
            for index, chunk in enumerate(session.last_chunks, start=1):
                print(f"  [{index}] {chunk.metadata}")
    except (EOFError, KeyboardInterrupt):
        print()


if __name__ == "__main__":
    main()