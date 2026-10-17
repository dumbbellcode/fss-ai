#!/usr/bin/env python3
"""Clean Markdown files produced from PDF text extraction."""

import argparse
import re
from pathlib import Path


def cleanup_regulation(md_path: str | Path, output_md_path: str | Path) -> None:
    """Clean an extracted Markdown file and write the result to another file.

    The cleanup removes known PDF header/footer blocks while preserving the
    remaining text. Gazette regulations are printed Hindi-first, English-second,
    so the leading Hindi block (real Devanagari *or* a legacy-font transliteration)
    is cut at the English start and any stray Devanagari line is dropped. An
    already-English document is left untouched. Line endings and whitespace are
    normalised.
    """
    input_path = Path(md_path)
    output_path = Path(output_md_path)

    lines = input_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    def normalized(line: str) -> str:
        return re.sub(r"\s+", " ", line).strip()

    lines = _cut_leading_hindi(lines, normalized)

    patterns = tuple(
        re.compile(re.escape(pattern))
        for pattern in (
            "Hkkjr dk jkti=k % vlk/kj.k",
            "THE  GAZETTE  OF  INDIA  :  EXTRAORDINARY",
        )
    )
    lines_to_remove = {
        index + offset
        for index, line in enumerate(lines)
        if any(pattern.search(line) for pattern in patterns)
        for offset in (-1, 0, 1)
        if 0 <= index + offset < len(lines)
    }
    text = "\n".join(line.rstrip() for index, line in enumerate(lines) if index not in lines_to_remove)
    text = _drop_devanagari_lines(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{text}\n", encoding="utf-8")


def _notification_header_index(lines: list[str], normalized) -> int | None:
    """Find the line where the notification begins.

    Matches the notification header in its known shapes, ignoring leading
    markdown heading markers (``#``/``##``) and stray whitespace:

    1. ``FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA NOTIFICATION`` on one line
       (date line such as ``New Delhi, the 29 th December, 2020`` follows). The
       authority may be wrapped in parentheses, e.g. ``(Food Safety and
       Standards Authority of India) NOTIFICATION``.
    2. ``FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA`` directly followed by a
       ``NOTIFICATION`` line.
    3. A ``NOTIFICATION`` line alone followed by a date line such as
       ``New Delhi, the 4 th November, 2015`` (no authority heading, e.g. when
       the ministry heading sits above it).

    When none of these match, fall back to :func:`_english_notification_index`.
    """
    heading = r"(?:#{1,6}\s*)?"
    authority_body = r"\(?\s*FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA\s*\)?"
    same_line = re.compile(rf"^{heading}{authority_body}\s+NOTIFICATION$", re.IGNORECASE)
    # Two-line header only for the plain (un-parenthesized) authority heading.
    authority = re.compile(rf"^{heading}FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA$", re.IGNORECASE)
    notification = re.compile(rf"^{heading}NOTIFICATION$", re.IGNORECASE)
    new_delhi = re.compile(r"^New Delhi,\s+the\s+.+$", re.IGNORECASE)

    for index, line in enumerate(lines):
        text = normalized(line)
        if same_line.match(text):
            return index
        if notification.match(text) and any(
            new_delhi.match(normalized(following)) for following in lines[index + 1 : index + 3]
        ):
            return index
        if authority.match(text):
            next_index = index + 1
            while next_index < len(lines) and not normalized(lines[next_index]):
                next_index += 1
            if next_index < len(lines) and notification.match(normalized(lines[next_index])):
                return index
    return _english_notification_index(lines, normalized)


_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
# English-only anchors for the notification. The Hindi version writes New Delhi as
# "नई दिल्ली" and never uses the FSSAI preamble, so these never occur in a Hindi
# block. Docling sometimes merges a Hindi fragment into the English authority /
# "NOTIFICATION" line and/or separates "New Delhi, the <date>" from the heading by
# several Hindi lines, which defeats the strict shapes above.
_ENGLISH_DATE_RE = re.compile(r"New Delhi,\s+the\b[^\n]*\b(?:19|20)\d{2}\b", re.IGNORECASE)
_ENGLISH_NOTICE_RE = re.compile(
    r"(?:FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA|\bNOTIFICATION\b|\bF\.?\s*No\.)",
    re.IGNORECASE,
)


def _english_notification_index(lines: list[str], normalized) -> int | None:
    """Locate the start of the English notification by its English-only anchors.

    Anchors on the English date line (``New Delhi, the <date>``) or an English
    authority/``NOTIFICATION``/``F. No.`` marker, then walks back over adjacent
    English/blank lines to keep the English preamble. Stops at any line that
    contains Devanagari so it cannot run back into the Hindi block.
    """
    for index, line in enumerate(lines):
        text = normalized(line)
        if not (_ENGLISH_DATE_RE.search(text) or _ENGLISH_NOTICE_RE.search(text)):
            continue
        # An anchor must be at least partly English (skip pure-Devanagari lines).
        if _DEVANAGARI_RE.search(text) and not _ASCII_LETTER_RE.search(text):
            continue
        start = index
        back = index - 1
        while back >= 0 and index - back <= 8:
            candidate = normalized(lines[back])
            if not candidate:
                back -= 1
                continue
            if _DEVANAGARI_RE.search(candidate):
                break
            start = back
            back -= 1
        return start
    return None


def _drop_devanagari_lines(text: str) -> str:
    """Remove lines whose letters are mostly Devanagari.

    After cutting at the English notification, docling can leave stray Hindi
    fragments at the seam; some notifications also interleave the Hindi and
    English text line by line. A line is dropped only when it contains Devanagari
    and has more Devanagari letters than Latin ones, so mixed lines that carry an
    English header/citation (where Latin letters dominate) are kept. If dropping
    would leave almost nothing, the text is returned unchanged to avoid ever
    producing an empty document.
    """
    kept = []
    for line in text.split("\n"):
        devanagari = len(_DEVANAGARI_RE.findall(line))
        latin = len(_ASCII_LETTER_RE.findall(line))
        if devanagari and devanagari > latin:
            continue
        kept.append(line)
    if any(line.strip() for line in kept):
        return "\n".join(kept)
    return text


# Lines that unambiguously start the English version of a gazette notification /
# regulation (the Hindi version never contains these English strings).
_ENGLISH_START_RE = re.compile(
    r"(?:MINISTRY OF HEALTH AND FAMILY WELFARE"
    r"|FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA"
    r"|^NOTIFICATION$"
    r"|F\.?\s*No\."
    r"|hereby makes the following"
    r"|Whereas\s+the\s+draft)",
    re.IGNORECASE,
)


def _first_english_start(lines: list[str], normalized) -> int | None:
    """Index of the first clearly-English notification/regulation start line."""
    for index, line in enumerate(lines):
        if _ENGLISH_START_RE.search(normalized(line)):
            return index
    return None


def _cut_leading_hindi(lines: list[str], normalized) -> list[str]:
    """Drop the Hindi block that precedes the English notification/regulation.

    Gazettes print the Hindi version first and the English version second, and
    the Hindi may be real Devanagari or a legacy-font transliteration. The block
    is cut only when Devanagari actually appears *before* the English start, so an
    already-English document (for example a consolidated compendium) is untouched.
    """
    hindi_indexes = [index for index, line in enumerate(lines) if _DEVANAGARI_RE.search(line)]
    if not hindi_indexes:
        return lines
    start = _first_english_start(lines, normalized)
    if start is None or not any(index < start for index in hindi_indexes):
        return lines
    return lines[start:]


def cleanup_amendment(md_path: str | Path, output_md_path: str | Path) -> None:
    """Clean an amendment Markdown file and write the result to another file."""
    input_path = Path(md_path)
    output_path = Path(output_md_path)
    lines = input_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    def normalized(line: str) -> str:
        return re.sub(r"\s+", " ", line).strip()

    notification_index = _notification_header_index(lines, normalized)
    if notification_index is not None:
        lines = lines[notification_index:]

    gazette_patterns = (
        re.compile(r"THE GAZETTE OF INDIA\s*:\s*EXTRAORDINARY", re.IGNORECASE),
        re.compile(r"भारत का रािपत्र\s*:\s*असाधारण"),
    )
    header_indexes = {
        index
        for index, line in enumerate(lines)
        if any(pattern.search(normalized(line)) for pattern in gazette_patterns)
    }

    # Page extraction can split the page number and gazette header over lines.
    def is_header_marker(line: str) -> bool:
        return bool(re.fullmatch(r"(?:\d+|[NT]|\[[^\]]+\])", normalized(line), re.IGNORECASE))

    for index in tuple(header_indexes):
        adjacent = index - 1
        while adjacent >= 0 and (not normalized(lines[adjacent]) or is_header_marker(lines[adjacent])):
            header_indexes.add(adjacent)
            adjacent -= 1

        adjacent = index + 1
        while adjacent < len(lines) and (not normalized(lines[adjacent]) or is_header_marker(lines[adjacent])):
            header_indexes.add(adjacent)
            adjacent += 1

    text = "\n".join(
        line.rstrip() for index, line in enumerate(lines) if index not in header_indexes
    )
    text = _drop_devanagari_lines(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{text}\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean an extracted Markdown file.")
    parser.add_argument("md_path", type=Path, help="Path to the input Markdown file")
    parser.add_argument("output_md_path", type=Path, help="Path for the cleaned Markdown file")
    parser.add_argument(
        "--kind",
        choices=("regulation", "amendment"),
        default="regulation",
        help="Document type to clean (default: regulation)",
    )
    args = parser.parse_args()

    cleaner = cleanup_amendment if args.kind == "amendment" else cleanup_regulation
    cleaner(args.md_path, args.output_md_path)
    print(f"Cleaned Markdown written to: {args.output_md_path}")


if __name__ == "__main__":
    main()
