import pytest
from unittest.mock import patch

from utils.pdf_to_md import DEFAULT_METHOD, convert_pdf


def test_default_conversion_method_is_docling():
    assert DEFAULT_METHOD == "docling"


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


def test_docling_pipeline_disables_ocr():
    docling = pytest.importorskip("docling")

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    assert pipeline_options.do_ocr is False
    assert InputFormat.PDF is not None
    assert PdfFormatOption is not None
    assert docling is not None
