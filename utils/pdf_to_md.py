#!/usr/bin/env python3
"""Convert a PDF to Markdown using PyMuPDF."""

import sys
from pathlib import Path
from typing import Literal

ConversionMethod = Literal["pymupdf", "markitdown"]

def convert_pdf(pdf_path: str | Path, method: ConversionMethod = "markitdown") -> Path:
    pdf_path = Path(pdf_path)
    output_path = pdf_path.with_name(f"{pdf_path.stem}.converted.md")

    if method == "markitdown":
        from markitdown import MarkItDown

        text = MarkItDown().convert(str(pdf_path)).text_content
    else:
        import pymupdf

        with pymupdf.open(pdf_path) as document:
            text = "\n".join(page.get_text() for page in document)

    output_path.write_text(f"{text.rstrip()}\n", encoding="utf-8")
    return output_path

def main():
    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] not in {"pymupdf", "markitdown"}):
        print("Usage: python pdf_to_md.py <pdf_path> [pymupdf|markitdown]")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    method = sys.argv[2] if len(sys.argv) == 3 else "markitdown"
    print(f"Converted to: {convert_pdf(pdf_path, method)}")

if __name__ == "__main__":
    main()
