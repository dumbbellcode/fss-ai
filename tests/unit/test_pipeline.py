import json
from pathlib import Path

from pre_processing.pipeline import Item, Manifest, Stage, run_pipeline


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_stages() -> list[Stage]:
    return [
        Stage("convert", "original", ".pdf", "converted", ".md", {"doc": lambda s, d: _write(d, "md:1")}),
        Stage("clean", "converted", ".md", "cleaned", ".md", {"doc": lambda s, d: _write(d, "md:2")}),
        Stage("parse", "cleaned", ".md", "cleaned", ".json", {"doc": lambda s, d: _write(d, '{"ok": true}')}),
    ]


def _make_item(tmp_path: Path) -> Item:
    _write(tmp_path / "original" / "reg.pdf", "pdf-bytes")
    return Item(kind="doc", base_stem="reg", root=tmp_path)


def _make_amendment_item(tmp_path: Path) -> Item:
    _write(tmp_path / "original" / "amendments" / "am.pdf", "pdf")
    return Item(kind="doc", base_stem="am", root=tmp_path, sub="amendments")


def _manifest(tmp_path: Path) -> Manifest:
    return Manifest(tmp_path / "manifest.json")


def test_full_run_creates_all_outputs(tmp_path):
    item = _make_item(tmp_path)
    results = run_pipeline([item], _make_stages(), _manifest(tmp_path))

    assert [r.stage for r in results] == ["convert", "clean", "parse"]
    assert all(not r.skipped for r in results)
    assert (tmp_path / "converted" / "reg.md").exists()
    assert (tmp_path / "cleaned" / "reg.md").exists()
    assert (tmp_path / "cleaned" / "reg.json").exists()


def test_amendments_preserve_subfolder(tmp_path):
    item = _make_amendment_item(tmp_path)
    results = run_pipeline([item], _make_stages(), _manifest(tmp_path))

    assert (tmp_path / "converted" / "amendments" / "am.md").exists()
    assert (tmp_path / "cleaned" / "amendments" / "am.md").exists()
    assert (tmp_path / "cleaned" / "amendments" / "am.json").exists()
    assert len(results) == 3


def test_incremental_run_skips_up_to_date(tmp_path):
    item = _make_item(tmp_path)
    manifest = _manifest(tmp_path)
    run_pipeline([item], _make_stages(), manifest)
    results = run_pipeline([item], _make_stages(), manifest)

    assert len(results) == 3
    assert all(r.skipped for r in results)
    assert (tmp_path / "converted" / "reg.md").read_text(encoding="utf-8") == "md:1"


def test_force_reruns_even_when_up_to_date(tmp_path):
    item = _make_item(tmp_path)
    manifest = _manifest(tmp_path)
    run_pipeline([item], _make_stages(), manifest)
    results = run_pipeline([item], _make_stages(), manifest, force=True)

    assert all(not r.skipped for r in results)


def test_subset_of_stages(tmp_path):
    item = _make_item(tmp_path)
    _write(tmp_path / "cleaned" / "reg.md", "md:2")
    results = run_pipeline([item], _make_stages(), _manifest(tmp_path), selected=["parse"])

    assert [r.stage for r in results] == ["parse"]
    assert not results[0].skipped
    assert not (tmp_path / "converted" / "reg.md").exists()


def test_source_change_triggers_rerun(tmp_path):
    item = _make_item(tmp_path)
    manifest = _manifest(tmp_path)
    run_pipeline([item], _make_stages(), manifest)

    (tmp_path / "original" / "reg.pdf").write_text("pdf-bytes-changed", encoding="utf-8")
    results = run_pipeline([item], _make_stages(), manifest)

    assert results[0].skipped is False
    assert (tmp_path / "converted" / "reg.md").read_text(encoding="utf-8") == "md:1"


def test_manifest_records_stages(tmp_path):
    item = _make_item(tmp_path)
    run_pipeline([item], _make_stages(), _manifest(tmp_path))

    data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    stages = {entry["stage"] for entry in data.values()}
    assert stages == {"convert", "clean", "parse"}


def test_manifest_persists_across_instances(tmp_path):
    item = _make_item(tmp_path)
    run_pipeline([item], _make_stages(), _manifest(tmp_path))

    fresh = Manifest(tmp_path / "manifest.json")
    assert fresh.is_current(tmp_path / "cleaned" / "reg.json", tmp_path / "cleaned" / "reg.md")


def test_only_predicate_restricts_stage(tmp_path):
    _write(tmp_path / "original" / "reg.pdf", "pdf")
    _write(tmp_path / "original" / "other.pdf", "pdf")
    stages = [
        Stage(
            "parse",
            "cleaned",
            ".md",
            "cleaned",
            ".json",
            {"doc": lambda s, d: _write(d, "{}")},
            only=lambda kind, stem: stem == "reg",
        )
    ]
    _write(tmp_path / "cleaned" / "reg.md", "md")
    _write(tmp_path / "cleaned" / "other.md", "md")
    results = run_pipeline(
        [
            Item(kind="doc", base_stem="reg", root=tmp_path),
            Item(kind="doc", base_stem="other", root=tmp_path),
        ],
        stages,
        _manifest(tmp_path),
    )

    assert [r.path.name for r in results] == ["reg.json"]
    assert not (tmp_path / "cleaned" / "other.json").exists()


def test_kind_selector_skips_unknown_kind(tmp_path):
    item = _make_item(tmp_path)
    stages = [Stage("convert", "original", ".pdf", "converted", ".md", {"other": lambda s, d: _write(d, "x")})]
    results = run_pipeline([item], stages, _manifest(tmp_path))
    assert results == []


def test_dependency_change_triggers_rerun(tmp_path):
    _write(tmp_path / "original" / "reg.pdf", "pdf")
    _write(tmp_path / "cleaned" / "reg.json", "{}")
    _write(tmp_path / "cleaned" / "amendments" / "a.json", '{"date": "2024-01-01"}')
    _write(tmp_path / "cleaned" / "amendments" / "b.json", '{"date": "2025-01-01"}')

    item = Item(kind="doc", base_stem="reg", root=tmp_path)
    stages = [
        Stage(
            "post",
            "cleaned",
            ".json",
            "post_amendment",
            ".final.json",
            {"doc": lambda s, d: _write(d, s.read_text(encoding="utf-8"))},
            dependencies=lambda item: [
                item.root / "cleaned" / f"{item.base_stem}.json",
                *sorted((item.root / "cleaned" / "amendments").glob("*.json")),
            ],
        )
    ]
    manifest = _manifest(tmp_path)
    run_pipeline([item], stages, manifest)
    first = run_pipeline([item], stages, manifest)
    assert all(r.skipped for r in first)

    (tmp_path / "cleaned" / "amendments" / "b.json").write_text('{"date": "2026-01-01"}', encoding="utf-8")
    second = run_pipeline([item], stages, manifest)
    assert not second[0].skipped