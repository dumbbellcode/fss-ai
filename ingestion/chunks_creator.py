#!/usr/bin/env python3
"""Create text chunks from a parsed regulation JSON for embedding and retrieval.

Each chapter section/subsection becomes one or more chunks of the form::

    Chapter: <chapter title>
    Section: <section text>

    <subsection text>

Every chunk carries metadata for the document it came from: ``regulation``
(the ``Regulation.title`` value), plus ``chapter``,
``section`` and ``subsection`` numbers. Subsections (and schedule/annexure/form
bodies) longer than ``chunk_size_tokens`` tokens are split into multiple
chunks using a LangChain ``RecursiveCharacterTextSplitter`` sized in tokens.
"""

import argparse
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field
import tiktoken

from ingestion.config import CHUNK_OVERLAP_TOKENS, CHUNK_SIZE_TOKENS, SPLIT_SEPARATORS
from pre_processing.regulation_parser import Regulation

_encoding = tiktoken.get_encoding("cl100k_base")


def _token_len(text: str) -> int:
    return len(_encoding.encode(text))


class ItemKind(StrEnum):
    """Non-section document items a chunk can represent."""

    SCHEDULE = "schedule"
    ANNEXURE = "annexure"
    FORM = "form"


class ChunkMetadata(BaseModel):
    """Metadata attached to every chunk, locating the text it came from.

    ``regulation`` is always present. The remaining fields are populated based
    on the item kind: chapter/section/subsection chunks set ``chapter``,
    ``section`` and ``subsection``; schedule/annexure/form chunks set ``kind``
    plus ``schedule``/``annexure``/``form``. ``part`` marks the 1-based index
    when a body longer than the chunk size was split into several chunks.
    """

    regulation: str = Field(description="Name of the directory holding the regulation JSON.")
    chapter: int | None = Field(default=None, description="Chapter number.")
    section: str | None = Field(default=None, description="Section number, e.g. '1.1'.")
    subsection: str | None = Field(default=None, description="Subsection number, e.g. '1.1.1'.")
    kind: ItemKind | None = Field(
        default=None, description="Document item kind for non-section content."
    )
    schedule: str | None = Field(default=None, description="Schedule name, e.g. 'Schedule 2'.")
    annexure: str | None = Field(default=None, description="Annexure name, e.g. 'Annexure-3'.")
    form: str | None = Field(default=None, description="Form name, e.g. 'Form D-2'.")
    part: int | None = Field(default=None, description="1-based index when a body was split into multiple chunks.")


@dataclass
class Chunk:
    text: str
    metadata: ChunkMetadata = field(default_factory=lambda: ChunkMetadata(regulation=""))

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, ChunkMetadata):
            self.metadata = ChunkMetadata.model_validate(self.metadata)


def _split_long_text(text: str, chunk_size_tokens: int, chunk_overlap_tokens: int) -> list[str]:
    """Split ``text`` into one or more parts, splitting only when it is long.

    Length is measured in tokens (``cl100k_base``); only bodies over
    ``chunk_size_tokens`` tokens are actually split into multiple chunks.
    """
    text = text.strip()
    if not text:
        return []
    if _token_len(text) <= chunk_size_tokens:
        return [text]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size_tokens,
        chunk_overlap=chunk_overlap_tokens,
        separators=SPLIT_SEPARATORS,
        length_function=_token_len,
    )
    return [part.strip() for part in splitter.split_text(text) if part.strip()]


def _emit(
    header: str,
    body: str,
    base_meta: dict,
    chunks: list[Chunk],
    chunk_size_tokens: int,
    chunk_overlap_tokens: int,
) -> None:
    parts = _split_long_text(body, chunk_size_tokens, chunk_overlap_tokens)
    for index, part in enumerate(parts, start=1):
        meta = dict(base_meta)
        if len(parts) > 1:
            meta["part"] = index
        chunks.append(Chunk(text=f"{header}\n\n{part}".strip(), metadata=meta))


def create_chunks(
    regulation: Regulation,
    chunk_size_tokens: int = CHUNK_SIZE_TOKENS,
    chunk_overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Chunk a parsed ``Regulation`` into embedding-ready text chunks.

    The regulation title is copied into chunk metadata. ``chunk_size_tokens``
    and ``chunk_overlap_tokens`` override the config defaults (useful when
    benchmarking different chunking strategies).
    """
    chunks: list[Chunk] = []

    for chapter in regulation.chapters:
        for form in chapter.forms:
            _emit(
                header=f"Chapter: {chapter.get_chunk_title()}\nForm: {form.name}",
                body=form.text,
                base_meta={
                    "regulation": regulation.title,
                    "chapter": chapter.no,
                    "kind": ItemKind.FORM,
                    "form": form.name,
                },
                chunk_size_tokens=chunk_size_tokens,
                chunk_overlap_tokens=chunk_overlap_tokens,
                chunks=chunks,
            )
        for section in chapter.sections:
            for subsection in section.sub_sections:
                _emit(
                    header=subsection.get_chunk_header(chapter, section),
                    body=subsection.text,
                    base_meta={
                        "regulation": regulation.title,
                        "chapter": chapter.no,
                        "section": section.no,
                        "subsection": subsection.no,
                    },
                    chunk_size_tokens=chunk_size_tokens,
                    chunk_overlap_tokens=chunk_overlap_tokens,
                    chunks=chunks,
                )

    for schedule in regulation.schedules:
        schedule_name = schedule.name
        _emit(
            header=f"Schedule: {schedule_name}",
            body=schedule.text,
            base_meta={"regulation": regulation.title, "kind": ItemKind.SCHEDULE, "schedule": schedule_name},
            chunk_size_tokens=chunk_size_tokens,
            chunk_overlap_tokens=chunk_overlap_tokens,
            chunks=chunks,
        )
        for form in schedule.forms:
            _emit(
                header=f"Schedule: {schedule_name}\nForm: {form.name}",
                body=form.text,
                base_meta={
                    "regulation": regulation.title,
                    "kind": ItemKind.FORM,
                    "schedule": schedule_name,
                    "form": form.name,
                },
                chunk_size_tokens=chunk_size_tokens,
                chunk_overlap_tokens=chunk_overlap_tokens,
                chunks=chunks,
            )
        for annexure in schedule.annexures:
            _emit(
                header=f"Schedule: {schedule_name}\nAnnexure: {annexure.name}",
                body=annexure.text,
                base_meta={
                    "regulation": regulation.title,
                    "kind": ItemKind.ANNEXURE,
                    "schedule": schedule_name,
                    "annexure": annexure.name,
                },
                chunk_size_tokens=chunk_size_tokens,
                chunk_overlap_tokens=chunk_overlap_tokens,
                chunks=chunks,
            )

    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Create text chunks from a parsed regulation JSON.")
    parser.add_argument("regulation_json_path", type=Path)
    parser.add_argument("output_json_path", type=Path)
    args = parser.parse_args()

    path = Path(args.regulation_json_path)
    regulation = Regulation.model_validate_json(path.read_text(encoding="utf-8"))
    chunks = create_chunks(regulation)
    args.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_json_path.write_text(
        json.dumps(
            [{"text": chunk.text, "metadata": chunk.metadata.model_dump()} for chunk in chunks],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(chunks)} chunks to: {args.output_json_path}")


if __name__ == "__main__":
    main()
