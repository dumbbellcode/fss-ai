#!/usr/bin/env python3
"""Clean Markdown files produced from PDF text extraction."""

import argparse
import re
from pathlib import Path


def cleanup_regulation(md_path: str | Path, output_md_path: str | Path) -> None:
    """Clean an extracted Markdown file and write the result to another file.

    The cleanup removes known PDF header/footer blocks while preserving the
    remaining text. It also normalizes line endings and whitespace.
    """
    input_path = Path(md_path)
    output_path = Path(output_md_path)

    lines = input_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").split("\n")
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
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{text}\n", encoding="utf-8")


def cleanup_amendment(md_path: str | Path, output_md_path: str | Path) -> None:
    """Clean an amendment Markdown file and write the result to another file."""
    input_path = Path(md_path)
    output_path = Path(output_md_path)
    lines = input_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    def normalized(line: str) -> str:
        return re.sub(r"\s+", " ", line).strip()

    notification_index = next(
        (
            index
            for index, line in enumerate(lines)
            if normalized(line).upper() == "NOTIFICATION"
            and any(
                re.match(r"^New Delhi,\s+the\s+.+$", normalized(next_line), re.IGNORECASE)
                for next_line in lines[index + 1 : index + 3]
            )
        ),
        None,
    )
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
