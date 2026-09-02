import json
from pathlib import Path

import pytest

from ingestion.chunks_creator import ItemKind, create_chunks
from pre_processing.regulation_parser import Regulation

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "regulation.json"


def _chunks(path: Path, regulation_name: str | None = None) -> list:
    regulation = Regulation.model_validate_json(path.read_text(encoding="utf-8"))
    if regulation_name:
        regulation.title = regulation_name
    return create_chunks(regulation)


def test_short_subsection_yields_single_chunk():
    chunks = _chunks(FIXTURE)
    one = [c for c in chunks if c.metadata.subsection == "1.1.1"]
    assert len(one) == 1
    chunk = one[0]
    assert chunk.text.startswith("Chapter: GENERAL\nSection: 1.1: Short title and commencement-")
    assert "\n\n1.1.1: These regulations may be called" in chunk.text
    assert chunk.metadata.regulation == FIXTURE.parent.name
    assert chunk.metadata.chapter == 1
    assert chunk.metadata.section == "1.1"
    assert chunk.metadata.subsection == "1.1.1"
    assert chunk.metadata.part is None


def test_long_subsection_is_split_into_parts():
    chunks = _chunks(FIXTURE)
    parts = sorted(
        (c for c in chunks if c.metadata.subsection == "1.2.1"),
        key=lambda c: c.metadata.part,
    )
    assert len(parts) > 1
    for index, chunk in enumerate(parts, start=1):
        assert chunk.metadata.part == index
        assert chunk.text.startswith("Chapter: GENERAL\nSection: 1.2: Definitions-\n\n")
        assert len(chunk.text) > 0


def test_schedule_annexure_and_form_chunks_are_created(tmp_path):
    regulation = {
        "title": "test_regulation",
        "chapters": [
            {
                "no": 1,
                "title": "GENERAL",
                "forms": [{"name": "Form A", "text": "A chapter-level form body."}],
                "sections": [],
            }
        ],
        "schedules": [
            {
                "name": "Schedule 1",
                "text": "Long schedule body " * 200,
                "forms": [{"name": "Form B", "text": "A schedule form body."}],
                "annexures": [{"name": "Annexure-1", "text": "An annexure body."}],
            }
        ],
    }
    path = tmp_path / "regulation.json"
    path.write_text(json.dumps(regulation), encoding="utf-8")

    chunks = _chunks(path)
    kinds = {c.metadata.kind for c in chunks}
    assert {ItemKind.SCHEDULE, ItemKind.ANNEXURE, ItemKind.FORM} <= kinds

    schedule = [c for c in chunks if c.metadata.kind is ItemKind.SCHEDULE]
    assert len(schedule) > 1
    assert all(c.text.startswith("Schedule: Schedule 1") for c in schedule)


def test_chunks_cover_every_subsection():
    chunks = _chunks(FIXTURE)
    subsections = {c.metadata.subsection for c in chunks if c.metadata.subsection}
    assert subsections == {"1.1.1", "1.1.2", "1.2.1", "2.1.1", "2.1.2", "2.1.7"}


def test_override_regulation_name():
    regulation = Regulation.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    regulation.title = "my_regulation"
    chunks = create_chunks(regulation)
    assert all(chunk.metadata.regulation == "my_regulation" for chunk in chunks)


def test_every_chunk_has_text_and_metadata():
    chunks = _chunks(FIXTURE)
    assert chunks
    assert all(chunk.text and chunk.metadata.regulation for chunk in chunks)


def test_chunk_size_override_changes_split_count():
    regulation = Regulation.model_validate_json(FIXTURE.read_text(encoding="utf-8"))

    def chunk_count(chunk_size_tokens, chunk_overlap_tokens=0):
        return len(
            create_chunks(
                regulation,
                chunk_size_tokens=chunk_size_tokens,
                chunk_overlap_tokens=chunk_overlap_tokens,
            )
        )

    coarse = chunk_count(1000)
    fine = chunk_count(100)
    assert fine > coarse


def test_metadata_is_validated_model():
    from ingestion.chunks_creator import Chunk, ChunkMetadata

    chunk = Chunk(text="x", metadata={"regulation": "r", "chapter": 1})
    assert isinstance(chunk.metadata, ChunkMetadata)

    schema = ChunkMetadata.model_json_schema()
    assert schema["required"] == ["regulation"]
    props = set(schema["properties"])
    assert {
        "regulation",
        "chapter",
        "section",
        "subsection",
        "kind",
        "schedule",
        "annexure",
        "form",
        "part",
    } <= props


def test_metadata_kind_is_enum_validated():
    from pydantic import ValidationError

    from ingestion.chunks_creator import Chunk

    chunk = Chunk(text="x", metadata={"regulation": "r", "kind": "form"})
    assert chunk.metadata.kind is ItemKind.FORM

    with pytest.raises(ValidationError):
        Chunk(text="x", metadata={"regulation": "r", "kind": "banana"})
