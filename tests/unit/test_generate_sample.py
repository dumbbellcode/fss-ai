import pytest

from utils.generate_sample import ALL_STAGE_NAMES, build_stages, parse_stages


def test_parse_stages_default_is_all():
    assert parse_stages(None) == list(ALL_STAGE_NAMES)


def test_parse_stages_subset():
    assert parse_stages("clean,parse") == ["clean", "parse"]


def test_parse_stages_ignores_empty_and_whitespace():
    assert parse_stages(" convert , , parse ") == ["convert", "parse"]


def test_parse_stages_rejects_unknown():
    with pytest.raises(ValueError):
        parse_stages("convert,download")


def test_build_stages_order():
    stages = build_stages("markitdown")
    assert [s.name for s in stages] == ["convert", "clean", "parse", "post_amendment", "ingestion"]


def test_build_stages_kind_processors():
    stages = build_stages("markitdown")
    clean = next(s for s in stages if s.name == "clean")
    assert set(clean.process) == {"regulation", "amendment"}
    parse = next(s for s in stages if s.name == "parse")
    assert set(parse.process) == {"regulation", "amendment"}
    assert parse.in_dir == "cleaned"
    assert parse.out_dir == "parsed"


def test_post_amendment_stage_config():
    stage = next(s for s in build_stages("markitdown") if s.name == "post_amendment")
    assert stage.in_dir == "parsed"
    assert stage.in_ext == ".json"
    assert stage.out_dir == "post_amendment"
    assert stage.out_ext == ".final.json"
    assert set(stage.process) == {"regulation"}
    assert stage.only("regulation", "Regulation") is True
    assert stage.only("regulation", "Compendium") is False
    assert stage.only("amendment", "anything") is False
    assert stage.dependencies is not None


def test_ingestion_stage_config():
    stage = next(s for s in build_stages("markitdown") if s.name == "ingestion")
    assert stage.in_dir == "post_amendment"
    assert stage.in_ext == ".final.json"
    assert stage.out_dir == "ingestion"
    assert stage.out_ext == ".ingested.json"
    assert set(stage.process) == {"regulation"}
    assert stage.only("regulation", "Regulation") is True
    assert stage.only("regulation", "Compendium") is False
    assert stage.only("amendment", "anything") is False
    assert stage.dependencies is not None
