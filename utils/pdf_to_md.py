#!/usr/bin/env python3
"""Convert a PDF to Markdown (default engine: docling)."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Literal

ConversionMethod = Literal["pymupdf", "markitdown", "docling"]

DEFAULT_METHOD: ConversionMethod = "docling"

# OCR languages for scanned notifications. Most FSSAI scans are English-only
# (``eng``); the bilingual Hindi-first gazettes need ``eng,hin`` (the ``hin``
# model must be installed for tesseract, e.g. ``brew install tesseract-lang``).
DEFAULT_OCR_LANGUAGES = ("eng",)


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


def _pdf_text_chars(pdf_path: Path) -> int:
    """Return the number of characters in the PDF's text layer."""
    import pymupdf

    with pymupdf.open(pdf_path) as document:
        return len("".join(page.get_text() for page in document).strip())


def _pdf_has_text_layer(pdf_path: Path, minimum_chars: int = 100) -> bool:
    """Whether the PDF carries an extractable text layer.

    Scanned gazette notifications have virtually no text; those need OCR, while
    a normal FSSAI PDF has a text layer and OCR would only add noise.
    """
    return _pdf_text_chars(pdf_path) >= minimum_chars


def _ocr_languages() -> list[str]:
    """OCR languages to request, from ``FSSAI_OCR_LANGS`` (comma separated)."""
    raw = os.environ.get("FSSAI_OCR_LANGS", ",".join(DEFAULT_OCR_LANGUAGES))
    return [code.strip() for code in raw.split(",") if code.strip()] or list(DEFAULT_OCR_LANGUAGES)


def _installed_ocr_languages() -> set[str] | None:
    """Languages installed for the Tesseract CLI, or None if it cannot be probed."""
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"], capture_output=True, text=True, check=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # The first line is a header ("List of available languages in ...").
    return {line.strip() for line in result.stdout.splitlines()[1:] if line.strip()}


def _resolve_ocr_languages() -> list[str]:
    """Drop OCR languages that are not installed so tesseract does not abort."""
    languages = _ocr_languages()
    installed = _installed_ocr_languages()
    if installed is None:
        return languages
    missing = [code for code in languages if code not in installed]
    if missing:
        print(
            f"Warning: OCR language(s) {missing} not installed for tesseract; "
            f"installed: {sorted(installed)}.",
            file=sys.stderr,
        )
    return [code for code in languages if code in installed]


def _convert_with_docling(pdf_path: Path) -> str:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    # FSSAI PDFs normally have a text layer, so OCR is disabled for speed and
    # fidelity; it is only enabled for the few scanned notifications that would
    # otherwise convert to nothing.
    pipeline_options.do_ocr = not _pdf_has_text_layer(pdf_path)
    if pipeline_options.do_ocr:
        languages = _resolve_ocr_languages()
        if not languages:
            print(f"Warning: no OCR language installed; converting {pdf_path} without OCR.", file=sys.stderr)
            pipeline_options.do_ocr = False
        else:
            from docling.datamodel.pipeline_options import TesseractCliOcrOptions

            pipeline_options.ocr_options = TesseractCliOcrOptions(lang=languages)
            pipeline_options.ocr_options.force_full_page_ocr = True
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
