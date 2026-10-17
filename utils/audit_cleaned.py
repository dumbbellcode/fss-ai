"""Cross-check the clean stage: every converted/*.md vs its cleaned/*.md.

Offline (no API calls). Flags files where the cleaned output looks incomplete,
was cut too early, still starts with Hindi, or is missing entirely.

Usage:
    python utils/audit_cleaned.py                 # every chapter
    python utils/audit_cleaned.py --dirs 01_,10_  # prefix filter
    python utils/audit_cleaned.py --verbose
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

REGULATIONS_DIR = Path("assets/regulations")

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_IMAGE_RE = re.compile(r"<!--\s*image", re.IGNORECASE)
# Marker that the English notification actually survived the Hindi cut.
_ENGLISH_ANCHOR_RE = re.compile(
    r"(?:F\.?\s*No\.|NOTIFICATION|Food Products Standards|Regulations?,\s*20\d\d|New Delhi)",
    re.IGNORECASE,
)
# Scanned Hindi pages OCR'd with the wrong model become Latin gibberish
# ("wg feeet, 4 ard, 2011"), which no Devanagari check can see.
_COMMON_ENGLISH_RE = re.compile(
    r"\b(?:the|and|of|to|in|for|a|is|be|shall|may|not|or|as|on|by|with|that|"
    r"India|Government|Food|Safety|Standards|Regulations?|Act|section|No)\b",
    re.IGNORECASE,
)
_MIN_PREFIX_WORDS = 25
_MAX_PREFIX_ENGLISH_RATIO = 0.15
_PREFIX_LINES = 25

MIN_MEANINGFUL_CHARS = 200
HEAVY_LOSS_RATIO = 0.35
MAX_HINDI_LINES = 3
REGULATION_MIN_RATIO = 0.8


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _deva_lines(text: str) -> int:
    count = 0
    for line in text.split("\n"):
        if len(_DEVANAGARI_RE.findall(line)) > len(_LATIN_RE.findall(line)) and _DEVANAGARI_RE.search(line):
            count += 1
    return count


def _first_content_line(text: str) -> str:
    for line in text.split("\n"):
        if line.strip():
            return line
    return ""


def _starts_with_hindi(text: str) -> bool:
    line = _first_content_line(text)
    return bool(_DEVANAGARI_RE.search(line)) and len(_DEVANAGARI_RE.findall(line)) >= len(_LATIN_RE.findall(line))


def _starts_with_non_english(text: str) -> bool:
    """Detect an OCR'd Hindi block that came out as Latin gibberish."""
    prefix = [line for line in text.split("\n") if line.strip()][:_PREFIX_LINES]
    words = re.findall(r"[A-Za-z]{2,}", " ".join(prefix))
    if len(words) < _MIN_PREFIX_WORDS:
        return False
    english = len(_COMMON_ENGLISH_RE.findall(" ".join(prefix)))
    return english / len(words) < _MAX_PREFIX_ENGLISH_RATIO


@dataclass
class CleanReport:
    path: Path
    kind: str
    conv_chars: int = 0
    clean_chars: int = 0
    image_only: bool = False
    hindi_before: int = 0
    hindi_after: int = 0
    flags: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.flags


def _check(conv_path: Path, clean_path: Path, kind: str) -> CleanReport:
    report = CleanReport(path=clean_path, kind=kind)
    converted = conv_path.read_text(encoding="utf-8")
    report.conv_chars = len(converted.strip())
    report.hindi_before = _deva_lines(converted)
    report.image_only = bool(_IMAGE_RE.search(converted)) and report.conv_chars < 4000

    if not clean_path.exists():
        report.flags.append("missing")
        return report

    cleaned = clean_path.read_text(encoding="utf-8")
    report.clean_chars = len(cleaned.strip())
    report.hindi_after = _deva_lines(cleaned)

    if report.image_only:
        # The PDF has no extractable text; a near-empty cleaned file is expected.
        return report

    if report.clean_chars == 0:
        report.flags.append("empty")
        return report
    if report.conv_chars >= MIN_MEANINGFUL_CHARS and report.clean_chars < MIN_MEANINGFUL_CHARS:
        report.flags.append("tiny")

    if _starts_with_hindi(cleaned):
        report.flags.append("starts_with_hindi")
    if _starts_with_non_english(cleaned):
        report.flags.append("starts_with_non_english")
    if kind == "amendment" and not _ENGLISH_ANCHOR_RE.search(cleaned):
        report.flags.append("no_english_anchor")

    # The cleaned text is produced by deleting lines, so its tail must still occur
    # verbatim in the converted document. If it does not, the cleaner fabricated or
    # truncated the output.
    tail = _norm(cleaned)[-120:]
    if tail and tail not in _norm(converted):
        report.flags.append("tail_not_in_source")

    if kind == "amendment":
        if report.clean_chars < HEAVY_LOSS_RATIO * report.conv_chars:
            report.flags.append("heavy_loss")
        if report.hindi_after > MAX_HINDI_LINES:
            report.flags.append(f"hindi_left={report.hindi_after}")
    else:
        if report.clean_chars < REGULATION_MIN_RATIO * report.conv_chars:
            report.flags.append("heavy_loss")
    return report


def _iter_pairs(chapter: Path):
    converted_root = chapter / "converted"
    if not converted_root.is_dir():
        return
    for conv_path in sorted(converted_root.rglob("*.md")):
        rel = conv_path.relative_to(converted_root)
        kind = "amendment" if rel.parts[0] == "amendments" else "regulation"
        yield conv_path, chapter / "cleaned" / rel, kind


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dirs", default="", help="Comma-separated chapter prefixes (default: all).")
    parser.add_argument("--verbose", action="store_true", help="List every flagged file.")
    args = parser.parse_args()

    prefixes = tuple(p.strip() for p in args.dirs.split(",") if p.strip())
    chapters = sorted(
        p for p in REGULATIONS_DIR.iterdir() if p.is_dir() and (not prefixes or p.name.startswith(prefixes))
    )

    total = flagged_total = 0
    flagged: list[CleanReport] = []
    for chapter in chapters:
        reports = [(_check(conv, clean, kind), conv) for conv, clean, kind in _iter_pairs(chapter)]
        if not reports:
            print(f"{chapter.name:58s} (no converted/*.md)")
            continue
        bad = [r for r, _ in reports if not r.ok]
        total += len(reports)
        flagged_total += len(bad)
        flagged.extend(bad)
        hindi_before = sum(r.hindi_before for r, _ in reports)
        hindi_after = sum(r.hindi_after for r in (rep for rep, _ in reports))
        print(
            f"{chapter.name:58s} files={len(reports):3d} flagged={len(bad):3d} "
            f"hindi_lines {hindi_before:4d}->{hindi_after:3d}"
        )

    print(f"\nConverted files checked: {total}; flagged: {flagged_total}")
    if flagged:
        print("\nFlagged cleaned files:")
        for report in flagged:
            if args.verbose or report.flags[0] in {
                "missing",
                "empty",
                "tiny",
                "starts_with_hindi",
                "starts_with_non_english",
                "heavy_loss",
            }:
                print(
                    f"  {report.path}  [{report.kind}] conv={report.conv_chars} clean={report.clean_chars} "
                    f"hindi={report.hindi_after} {', '.join(report.flags)}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
