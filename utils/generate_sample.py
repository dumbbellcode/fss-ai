#!/usr/bin/env python3
"""Generate Markdown, cleaned Markdown, and JSON for sample regulations."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pre_processing.cleanup_markdown import cleanup_regulation
from pre_processing.regulation_parser import parse_regulation
from utils.pdf_to_md import ConversionMethod, convert_pdf


def process_pdf(pdf_path: Path, method: ConversionMethod) -> None:
    markdown_path = convert_pdf(pdf_path, method)
    cleaned_path = pdf_path.with_name(f"{pdf_path.stem}.cleaned.md")
    json_path = pdf_path.with_name(f"{pdf_path.stem}.cleaned.json")

    cleanup_regulation(markdown_path, cleaned_path)
    result = parse_regulation(cleaned_path)
    json_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")

    print(f"Processed: {pdf_path}")
    print(f"  Markdown: {markdown_path.name}")
    print(f"  Cleaned:  {cleaned_path.name}")
    print(f"  JSON:     {json_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the PDF-to-JSON preprocessing pipeline for sample directories."
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=2,
        help="Number of regulation directories to process (default: 2)",
    )
    parser.add_argument(
        "--method",
        choices=("markitdown", "pymupdf"),
        default="markitdown",
        help="PDF conversion method (default: markitdown)",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=PROJECT_ROOT / "assets" / "regulations",
        help="Directory containing regulation directories",
    )
    args = parser.parse_args()

    directories = sorted(path for path in args.assets_dir.iterdir() if path.is_dir())
    if args.sample_size < 1 or args.sample_size > len(directories):
        parser.error(f"--sample-size must be between 1 and {len(directories)}")

    for directory in directories[: args.sample_size]:
        for pdf_path in sorted(directory.glob("*.pdf")):
            process_pdf(pdf_path, args.method)


if __name__ == "__main__":
    main()
