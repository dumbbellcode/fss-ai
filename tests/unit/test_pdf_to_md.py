import pytest
from unittest.mock import patch

from utils.pdf_to_md import DEFAULT_METHOD, convert_pdf, is_pdf


def test_default_conversion_method_is_docling():
    assert DEFAULT_METHOD == "docling"


def test_is_pdf_checks_magic_bytes(tmp_path):
    real = tmp_path / "real.pdf"
    real.write_bytes(b"%PDF-1.7\nfake")
    html = tmp_path / "fake.pdf"
    html.write_bytes(b"<!DOCTYPE html><html>not a pdf</html>")

    assert is_pdf(real) is True
    assert is_pdf(html) is False
    assert is_pdf(tmp_path / "missing.pdf") is False


def test_convert_pdf_dispatches_to_docling_by_default(tmp_path):
    pdf = tmp_path / "Regulation.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    output = tmp_path / "Regulation.md"

    with patch("utils.pdf_to_md._convert_with_docling", return_value="# Docling\n") as converter:
        result = convert_pdf(pdf, output_path=output)

    converter.assert_called_once_with(pdf)
    assert result == output
    assert output.read_text(encoding="utf-8") == "# Docling\n"


def test_convert_pdf_explicit_docling_method(tmp_path):
    pdf = tmp_path / "Regulation.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    output = tmp_path / "Regulation.md"

    with patch("utils.pdf_to_md._convert_with_docling", return_value="| a | b |\n") as converter:
        convert_pdf(pdf, "docling", output_path=output)

    converter.assert_called_once_with(pdf)
    assert output.read_text(encoding="utf-8") == "| a | b |\n"


def test_pdf_has_text_layer_detects_scans(tmp_path):
    pytest.importorskip("pymupdf")
    import pymupdf

    from utils.pdf_to_md import _pdf_has_text_layer, _pdf_text_chars

    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text(
            (72, 72),
            "Food Safety and Standards (Food Products Standards and Food Additives)\n"
            "Regulations, 2011 - these are the principal regulations and they have\n"
            "a text layer that can be extracted without running OCR.",
        )
        text_pdf = tmp_path / "text.pdf"
        document.save(text_pdf)

    with pymupdf.open() as document:
        document.new_page()  # blank page => no text layer, like a scan
        scan_pdf = tmp_path / "scan.pdf"
        document.save(scan_pdf)

    assert _pdf_has_text_layer(text_pdf) is True
    assert _pdf_has_text_layer(scan_pdf) is False
    assert _pdf_text_chars(scan_pdf) == 0


def test_ocr_languages_come_from_env(monkeypatch):
    from utils import pdf_to_md as module

    monkeypatch.delenv("FSSAI_OCR_LANGS", raising=False)
    assert module._ocr_languages() == ["eng"]

    monkeypatch.setenv("FSSAI_OCR_LANGS", "eng, hin ,")
    assert module._ocr_languages() == ["eng", "hin"]

    monkeypatch.setenv("FSSAI_OCR_LANGS", " , ")
    assert module._ocr_languages() == ["eng"]


def test_resolve_ocr_languages_drops_missing_models(monkeypatch, capsys):
    from utils import pdf_to_md as module

    monkeypatch.setenv("FSSAI_OCR_LANGS", "eng,hin")
    monkeypatch.setattr(module, "_installed_ocr_languages", lambda: {"eng", "osd"})
    assert module._resolve_ocr_languages() == ["eng"]
    assert "hin" in capsys.readouterr().err

    # Probing failure (no tesseract binary) keeps the request untouched.
    monkeypatch.setattr(module, "_installed_ocr_languages", lambda: None)
    assert module._resolve_ocr_languages() == ["eng", "hin"]

    monkeypatch.setattr(module, "_installed_ocr_languages", lambda: set())
    assert module._resolve_ocr_languages() == []


def test_docling_enables_ocr_only_for_pdfs_without_a_text_layer(tmp_path, monkeypatch):
    pytest.importorskip("docling")
    from docling import document_converter as dc
    from docling.datamodel import pipeline_options as po

    from utils import pdf_to_md as module

    seen: dict = {}

    class SpyOptions(po.PdfPipelineOptions):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            seen["options"] = self

    class StubConverter:
        def __init__(self, *args, **kwargs):
            pass

        def convert(self, path):
            return type("R", (), {"document": type("D", (), {"export_to_markdown": lambda self: "text"})()})()

    monkeypatch.setattr(po, "PdfPipelineOptions", SpyOptions)
    monkeypatch.setattr(dc, "DocumentConverter", StubConverter)
    monkeypatch.setattr(module, "_installed_ocr_languages", lambda: {"eng"})

    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(module, "_pdf_has_text_layer", lambda path, minimum_chars=100: False)
    assert module._convert_with_docling(pdf) == "text"
    assert seen["options"].do_ocr is True
    assert list(seen["options"].ocr_options.lang) == ["eng"]

    monkeypatch.setattr(module, "_pdf_has_text_layer", lambda path, minimum_chars=100: True)
    assert module._convert_with_docling(pdf) == "text"
    assert seen["options"].do_ocr is False


def test_docling_skips_ocr_when_no_language_is_installed(tmp_path, monkeypatch):
    pytest.importorskip("docling")
    from docling import document_converter as dc
    from docling.datamodel import pipeline_options as po

    from utils import pdf_to_md as module

    seen: dict = {}

    class SpyOptions(po.PdfPipelineOptions):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            seen["options"] = self

    class StubConverter:
        def __init__(self, *args, **kwargs):
            pass

        def convert(self, path):
            return type("R", (), {"document": type("D", (), {"export_to_markdown": lambda self: "text"})()})()

    monkeypatch.setattr(po, "PdfPipelineOptions", SpyOptions)
    monkeypatch.setattr(dc, "DocumentConverter", StubConverter)
    monkeypatch.setattr(module, "_installed_ocr_languages", lambda: set())
    monkeypatch.setattr(module, "_pdf_has_text_layer", lambda path, minimum_chars=100: False)

    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    assert module._convert_with_docling(pdf) == "text"
    assert seen["options"].do_ocr is False
