#!/usr/bin/env python3
"""Convert a PDF to Markdown using PyMuPDF."""

import sys
from pathlib import Path

def convert_pdf(pdf_path):
    import pymupdf

    output_path = pdf_path.with_suffix(".md")
    with pymupdf.open(pdf_path) as document, output_path.open("w", encoding="utf-8") as output:
        for page in document:
            output.write(page.get_text())
            output.write("\n")
    return output_path

def main():
    if len(sys.argv) != 2:
        print("Usage: python pdf_to_md.py <pdf_path>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    print(f"Converted to: {convert_pdf(pdf_path)}")

if __name__ == "__main__":
    main()
