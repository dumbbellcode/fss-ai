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


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean an extracted Markdown file.")
    parser.add_argument("md_path", type=Path, help="Path to the input Markdown file")
    parser.add_argument("output_md_path", type=Path, help="Path for the cleaned Markdown file")
    args = parser.parse_args()

    cleanup_regulation(args.md_path, args.output_md_path)
    print(f"Cleaned Markdown written to: {args.output_md_path}")


if __name__ == "__main__":
    main()
