"""Audit parsed amendment JSON for signs of a failed extraction.

Run this after a parse pass to find files worth re-parsing with ``--force``.
It is offline (no API calls): it only compares the parsed JSON with the cleaned
markdown that produced it.

Usage:
    python utils/audit_parsed_amendments.py                 # every chapter
    python utils/audit_parsed_amendments.py --dirs 02_,04_  # prefix filter
    python utils/audit_parsed_amendments.py --verbose       # list every flagged file
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from pre_processing.amendment_parser import _has_change_instructions, _has_elision

REGULATIONS_DIR = Path("assets/regulations")

# Sentences that are the notification's boilerplate, never an amendment.
_BOILERPLATE_PREFIXES = (
    "now, therefore",
    "the food safety and standards authority of india hereby makes the following regulations",
    "and whereas",
    "whereas the draft",
)


def _is_boilerplate(text: str) -> bool:
    stripped = text.strip().lower()
    return any(stripped.startswith(prefix) for prefix in _BOILERPLATE_PREFIXES)


@dataclass
class FileReport:
    path: Path
    changes: int = 0
    empty_but_expected: bool = False
    elided: int = 0
    boilerplate: int = 0
    unreadable: str | None = None
    flags: list[str] = field(default_factory=list)

    @property
    def needs_rerun(self) -> bool:
        return bool(self.unreadable) or self.empty_but_expected or self.elided or self.boilerplate


def _audit_file(json_path: Path, md_path: Path | None) -> FileReport:
    report = FileReport(path=json_path)
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.unreadable = str(exc)
        return report

    changes = data.get("changes") or []
    report.changes = len(changes)

    if md_path is not None and md_path.exists():
        source = md_path.read_text(encoding="utf-8")
    else:
        source = ""

    if not changes and source and _has_change_instructions(source):
        report.empty_but_expected = True
        report.flags.append("empty")

    for change in changes:
        text = (change.get("amendment_text") or "") if isinstance(change, dict) else ""
        if _has_elision(text):
            report.elided += 1
        if _is_boilerplate(text):
            report.boilerplate += 1

    if report.elided:
        report.flags.append(f"elided={report.elided}")
    if report.boilerplate:
        report.flags.append(f"boilerplate={report.boilerplate}")
    if report.unreadable:
        report.flags.append("unreadable")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dirs",
        default="",
        help="Comma-separated chapter-name prefixes to include (default: all).",
    )
    parser.add_argument("--verbose", action="store_true", help="Print every flagged file.")
    args = parser.parse_args()

    prefixes = tuple(p.strip() for p in args.dirs.split(",") if p.strip())
    chapters = sorted(
        p
        for p in REGULATIONS_DIR.iterdir()
        if p.is_dir() and (not prefixes or p.name.startswith(prefixes))
    )
    if not chapters:
        print("No matching chapters found.")
        return 1

    total_files = 0
    flagged: list[FileReport] = []
    for chapter in chapters:
        parsed_dir = chapter / "parsed" / "amendments"
        cleaned_dir = chapter / "cleaned" / "amendments"
        if not parsed_dir.is_dir():
            print(f"{chapter.name:55s} (no parsed/amendments)")
            continue

        reports = [
            _audit_file(json_path, cleaned_dir / f"{json_path.stem}.md")
            for json_path in sorted(parsed_dir.glob("*.json"))
        ]
        total_files += len(reports)
        bad = [r for r in reports if r.needs_rerun]
        flagged.extend(bad)
        print(
            f"{chapter.name:55s} files={len(reports):3d}  "
            f"flagged={len(bad):3d}  empty={sum(r.empty_but_expected for r in reports):2d}  "
            f"elided={sum(r.elided for r in reports):3d}  boilerplate={sum(r.boilerplate for r in reports):3d}"
        )

    print(f"\nTotal parsed amendment files: {total_files}; flagged: {len(flagged)}")
    if flagged:
        print("\nFiles worth re-parsing (--stages parse --force):")
        for report in flagged:
            if report.unreadable and not args.verbose:
                print(f"  {report.path}  [UNREADABLE] {report.unreadable}")
                continue
            if args.verbose or report.needs_rerun:
                print(f"  {report.path}  changes={report.changes}  {', '.join(report.flags)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
