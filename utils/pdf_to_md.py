#!/usr/bin/env python3
"""Convert a PDF to Markdown (default engine: docling)."""

import sys
from pathlib import Path
from typing import Literal

ConversionMethod = Literal["pymupdf", "markitdown", "docling"]

DEFAULT_METHOD: ConversionMethod = "docling"


def is_pdf(path: Path) -> bool:
    """Return True if the file starts with PDF magic bytes.

    Some sources save HTML documents with a ``.pdf`` extension; those cannot
    be processed by PDF conversion engines and should be skipped by callers.
    """
    try:
        with path.open("rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def _convert_with_docling(pdf_path: Path) -> str:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    # FSSAI PDFs have a text layer, so OCR is disabled for speed and fidelity.
    pipeline_options.do_ocr = False
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    return converter.convert(str(pdf_path)).document.export_to_markdown()


def convert_pdf(
    pdf_path: str | Path,
    method: ConversionMethod = DEFAULT_METHOD,
    output_path: str | Path | None = None,
) -> Path:
    pdf_path = Path(pdf_path)
    output_path = Path(output_path) if output_path else pdf_path.with_name(f"{pdf_path.stem}.converted.md")

    if method == "docling":
        text = _convert_with_docling(pdf_path)
    elif method == "markitdown":
        from markitdown import MarkItDown

        text = MarkItDown().convert(str(pdf_path)).text_content
    else:
        import pymupdf

        with pymupdf.open(pdf_path) as document:
            text = "\n".join(page.get_text() for page in document)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{text.rstrip()}\n", encoding="utf-8")
    return output_path

def main():
    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] not in {"pymupdf", "markitdown", "docling"}):
        print("Usage: python pdf_to_md.py <pdf_path> [pymupdf|markitdown|docling]")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    method = sys.argv[2] if len(sys.argv) == 3 else DEFAULT_METHOD
    print(f"Converted to: {convert_pdf(pdf_path, method)}")

if __name__ == "__main__":
    main()
