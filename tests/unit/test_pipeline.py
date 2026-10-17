import json
from pathlib import Path

import pytest

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


def test_stages_complete_for_all_items_before_next_stage(tmp_path):
    first = _make_item(tmp_path / "first")
    second = _make_item(tmp_path / "second")
    results = run_pipeline([first, second], _make_stages(), _manifest(tmp_path))

    assert [result.stage for result in results] == [
        "convert",
        "convert",
        "clean",
        "clean",
        "parse",
        "parse",
    ]


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


def test_continue_on_error_records_failure_and_runs_rest(tmp_path):
    items = [
        Item(kind="doc", base_stem="bad", root=tmp_path),
        Item(kind="doc", base_stem="good", root=tmp_path),
    ]
    for item in items:
        _write(tmp_path / "original" / f"{item.base_stem}.pdf", "pdf")

    def _process(src: Path, dst: Path) -> None:
        if src.stem == "bad":
            raise RuntimeError("kaboom")
        _write(dst, "ok")

    stages = [Stage("convert", "original", ".pdf", "converted", ".md", {"doc": _process})]

    manifest = _manifest(tmp_path)
    results = run_pipeline(items, stages, manifest, continue_on_error=True)

    assert [r.path.name for r in results] == ["bad.md", "good.md"]
    assert results[0].error is not None and "kaboom" in results[0].error
    assert results[1].error is None
    assert (tmp_path / "converted" / "good.md").exists()
    assert not (tmp_path / "converted" / "bad.md").exists()
    # The failed item is not recorded, so a later run retries it.
    assert not manifest.is_current(tmp_path / "converted" / "bad.md", tmp_path / "original" / "bad.pdf")


def test_continue_on_error_false_raises(tmp_path):
    _write(tmp_path / "original" / "reg.pdf", "pdf")

    def _process(src: Path, dst: Path) -> None:
        raise RuntimeError("kaboom")

    stages = [Stage("convert", "original", ".pdf", "converted", ".md", {"doc": _process})]

    with pytest.raises(RuntimeError, match="kaboom"):
        run_pipeline([Item(kind="doc", base_stem="reg", root=tmp_path)], stages, _manifest(tmp_path))


def test_parallel_run_preserves_item_order(tmp_path):
    names = ("a", "b", "c", "d")
    items = []
    for name in names:
        _write(tmp_path / "original" / f"{name}.pdf", "pdf")
        items.append(Item(kind="doc", base_stem=name, root=tmp_path))

    stages = [Stage("convert", "original", ".pdf", "converted", ".md", {"doc": lambda s, d: _write(d, "md")})]
    manifest = _manifest(tmp_path)
    results = run_pipeline(items, stages, manifest, max_workers=4)

    assert [r.path.name for r in results] == [f"{n}.md" for n in names]
    assert all(r.error is None and not r.skipped for r in results)
    assert all((tmp_path / "converted" / f"{n}.md").exists() for n in names)


def test_parallel_run_is_incremental_on_rerun(tmp_path):
    _write(tmp_path / "original" / "a.pdf", "pdf")
    item = Item(kind="doc", base_stem="a", root=tmp_path)
    stages = [Stage("convert", "original", ".pdf", "converted", ".md", {"doc": lambda s, d: _write(d, "md")})]
    manifest = _manifest(tmp_path)

    run_pipeline([item], stages, manifest, max_workers=4)
    second = run_pipeline([item], stages, manifest, max_workers=4)

    assert all(r.skipped for r in second)


def test_parallel_run_executes_concurrently(tmp_path):
    import threading
    import time

    names = ("a", "b", "c", "d")
    items = []
    for name in names:
        _write(tmp_path / "original" / f"{name}.pdf", "pdf")
        items.append(Item(kind="doc", base_stem=name, root=tmp_path))

    lock = threading.Lock()
    state = {"active": 0, "peak": 0}

    def _process(src: Path, dst: Path) -> None:
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.05)
        with lock:
            state["active"] -= 1
        _write(dst, "md")

    stages = [Stage("convert", "original", ".pdf", "converted", ".md", {"doc": _process})]
    run_pipeline(items, stages, _manifest(tmp_path), max_workers=4)

    assert state["peak"] > 1


def test_parallel_run_isolates_failures(tmp_path):
    names = ("bad", "good")
    items = []
    for name in names:
        _write(tmp_path / "original" / f"{name}.pdf", "pdf")
        items.append(Item(kind="doc", base_stem=name, root=tmp_path))

    def _process(src: Path, dst: Path) -> None:
        if src.stem == "bad":
            raise RuntimeError("kaboom")
        _write(dst, "ok")

    stages = [Stage("convert", "original", ".pdf", "converted", ".md", {"doc": _process})]
    results = run_pipeline(items, stages, _manifest(tmp_path), max_workers=4, continue_on_error=True)

    assert [r.path.name for r in results] == ["bad.md", "good.md"]
    assert results[0].error is not None
    assert results[1].error is None


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
