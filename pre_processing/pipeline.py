#!/usr/bin/env python3
"""Reusable multi-stage file pipeline with manifest-based incremental processing.

Each stage transforms a file from one stage directory to the next, preserving
any relative subfolder (e.g. ``amendments/``). Layout per regulation directory::

    original/<stem>.pdf        (sources)
    converted/<stem>.md        (stage 1 output)
    cleaned/<stem>.md          (stage 2 output)
    parsed/<stem>.json         (stage 3 output)

A ``Manifest`` records a hash of each stage's source so up-to-date outputs can be
skipped on subsequent runs. Callers may select a subset of stages to run.
"""

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

ProcessFn = Callable[[Path, Path], None]
ProcessSelector = ProcessFn | dict[str, ProcessFn]
OnlyPredicate = Callable[[str, str], bool]
DependencyFn = Callable[["Item"], Sequence[Path]]


@dataclass(frozen=True)
class Stage:
    """A single transform in the pipeline.

    ``name`` identifies the stage (used by the CLI to select subsets).
    Inputs are read from ``in_dir`` and written to ``out_dir`` (both relative to
    the item's root directory), with the item's ``sub`` folder preserved.
    ``process`` is either a single callable or a dict keyed by item ``kind``.
    ``only`` optionally restricts which ``(kind, stem)`` items a stage applies to.
    ``dependencies`` optionally overrides the inputs hashed by the manifest (used
    when a stage's output depends on more files than its single source).
    """

    name: str
    in_dir: str
    in_ext: str
    out_dir: str
    out_ext: str
    process: ProcessSelector
    only: OnlyPredicate | None = None
    dependencies: DependencyFn | None = None


@dataclass
class Item:
    """A source file flowing through the pipeline."""

    kind: str
    base_stem: str
    root: Path
    sub: str = ""


@dataclass(frozen=True)
class PipelineResult:
    stage: str
    path: Path
    skipped: bool
    error: str | None = None


class Manifest:
    """Tracks the source hash for each produced output file."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, dict] = {}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _as_list(sources: Path | Sequence[Path]) -> list[Path]:
        return [sources] if isinstance(sources, Path) else list(sources)

    @staticmethod
    def _hash(sources: Sequence[Path]) -> str:
        digest = hashlib.sha256()
        for path in sorted(sources, key=lambda p: str(p)):
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def is_current(self, output: Path, sources: Path | Sequence[Path]) -> bool:
        sources = self._as_list(sources)
        if not output.exists() or any(not source.exists() for source in sources):
            return False
        entry = self.data.get(str(output))
        return bool(entry) and entry.get("hash") == self._hash(sources)

    def record(self, output: Path, sources: Path | Sequence[Path], stage: str) -> None:
        self.data[str(output)] = {"stage": stage, "hash": self._hash(self._as_list(sources))}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")


def _processor(stage: Stage, kind: str) -> ProcessFn | None:
    if isinstance(stage.process, dict):
        return stage.process.get(kind)
    return stage.process


def _applies(stage: Stage, item: Item) -> bool:
    return _processor(stage, item.kind) is not None and (
        stage.only is None or stage.only(item.kind, item.base_stem)
    )


def _stage_paths(stage: Stage, item: Item) -> tuple[Path, Path]:
    source = item.root / stage.in_dir / item.sub / f"{item.base_stem}{stage.in_ext}"
    output = item.root / stage.out_dir / item.sub / f"{item.base_stem}{stage.out_ext}"
    return source, output


def run_pipeline(
    items: Sequence[Item],
    stages: Sequence[Stage],
    manifest: Manifest,
    selected: Sequence[str] | None = None,
    force: bool = False,
    continue_on_error: bool = False,
    max_workers: int = 1,
) -> list[PipelineResult]:
    """Run ``items`` through ``stages``, skipping up-to-date outputs.

    ``selected`` restricts which stage names run; ``None`` means all stages.
    Returns one :class:`PipelineResult` per (item, stage) that applies, in
    item order.

    When ``continue_on_error`` is True, a failing item is recorded with its error
    message and the run proceeds to the remaining items (failures are reported in
    the returned results). Progress already saved to the manifest is never lost.

    ``max_workers`` > 1 processes the items of each stage concurrently. Stages are
    still run in order, so a stage only starts once the previous one is complete.
    """
    selected = set(selected) if selected is not None else None
    results: list[PipelineResult] = []
    manifest_lock = threading.Lock()

    for stage in stages:
        if selected is not None and stage.name not in selected:
            continue

        # Build the work plan for this stage, preserving item order.
        plans: list[tuple[Item, Path, Path, list[Path] | Sequence[Path], bool]] = []
        for item in items:
            if not _applies(stage, item):
                continue
            source, output = _stage_paths(stage, item)
            sources = stage.dependencies(item) if stage.dependencies else [source]
            skipped = not force and manifest.is_current(output, sources)
            plans.append((item, source, output, sources, skipped))

        stage_results: list[PipelineResult | None] = [None] * len(plans)

        def run_one(index: int) -> None:
            item, source, output, sources, skipped = plans[index]
            if skipped:
                stage_results[index] = PipelineResult(stage.name, output, True)
                return
            try:
                _processor(stage, item.kind)(source, output)
            except Exception as exc:  # noqa: BLE001 - surfaced in the result
                if not continue_on_error:
                    raise
                stage_results[index] = PipelineResult(
                    stage.name, output, False, f"{type(exc).__name__}: {exc}"
                )
                return
            with manifest_lock:
                manifest.record(output, sources, stage.name)
                manifest.save()
            stage_results[index] = PipelineResult(stage.name, output, False)

        indexes = range(len(plans))
        if max_workers > 1 and len(plans) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(run_one, index) for index in indexes]
                for future in futures:
                    future.result()
        else:
            for index in indexes:
                run_one(index)

        results.extend(result for result in stage_results if result is not None)

    manifest.save()
    return results
