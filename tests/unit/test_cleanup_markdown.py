import re

from pre_processing.cleanup_markdown import cleanup_amendment, cleanup_regulation


def test_cleanup_amendment_falls_back_to_authority_notification(tmp_path):
    source = tmp_path / "amendment.md"
    output = tmp_path / "cleaned.md"
    source.write_text(
        "Cover page\n"
        "FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA\n"
        "\n"
        "NOTIFICATION\n"
        "Amendment body\n",
        encoding="utf-8",
    )

    cleanup_amendment(source, output)

    cleaned = output.read_text(encoding="utf-8")
    assert cleaned.startswith("FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA\n\nNOTIFICATION")
    assert "Cover page" not in cleaned


def _assert_trimmed_to_notification(source_text, tmp_path, expected_prefix):
    source = tmp_path / "amendment.md"
    output = tmp_path / "cleaned.md"
    source.write_text(source_text, encoding="utf-8")

    cleanup_amendment(source, output)

    cleaned = output.read_text(encoding="utf-8")
    assert cleaned.startswith(expected_prefix)
    assert "Cover page" not in cleaned
    assert "Amendment body" in cleaned


def test_notification_header_same_line(tmp_path):
    _assert_trimmed_to_notification(
        "Cover page\n"
        "## FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA NOTIFICATION\n"
        "\n"
        "New Delhi, the 21st February, 2023\n"
        "\n"
        "Amendment body\n",
        tmp_path,
        "## FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA NOTIFICATION",
    )


def test_notification_header_splits_across_lines(tmp_path):
    _assert_trimmed_to_notification(
        "Cover page\n"
        "## FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA\n"
        "\n"
        "## NOTIFICATION\n"
        "\n"
        "Amendment body\n",
        tmp_path,
        "## FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA",
    )


def test_notification_header_with_ragged_date_spacing(tmp_path):
    _assert_trimmed_to_notification(
        "Cover page\n"
        "## FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA NOTIFICATION\n"
        "\n"
        "New Delhi, the  18th  March , 2021\n"
        "\n"
        "Amendment body\n",
        tmp_path,
        "## FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA NOTIFICATION",
    )


def test_notification_header_with_spaced_day_number(tmp_path):
    _assert_trimmed_to_notification(
        "Cover page\n"
        "## FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA NOTIFICATION\n"
        "\n"
        "New Delhi, the 29 th December, 2020\n"
        "\n"
        "Amendment body\n",
        tmp_path,
        "## FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA NOTIFICATION",
    )


def test_notification_header_alone_with_date(tmp_path):
    _assert_trimmed_to_notification(
        "Cover page\n"
        "## MINISTRY OF HEALTH AND FAMILY WELFARE\n"
        "\n"
        "(Food Safety and Standards Authority of India)\n"
        "\n"
        "## NOTIFICATION\n"
        "\n"
        "New Delhi, the   4 th November, 2015\n"
        "\n"
        "Amendment body\n",
        tmp_path,
        "## NOTIFICATION",
    )


def test_notification_header_parenthesized_authority(tmp_path):
    _assert_trimmed_to_notification(
        "Cover page\n"
        "## (Food Safety and Standards Authority of India) NOTIFICATION\n"
        "\n"
        "New Delhi, the 2nd September,2020\n"
        "\n"
        "Amendment body\n",
        tmp_path,
        "## (Food Safety and Standards Authority of India) NOTIFICATION",
    )


def _hindi_line():
    return "िकसी िवभाग का पाठ यहाँ िलखा गया है"


def test_cleanup_cuts_hindi_block_before_english_date(tmp_path):
    source = tmp_path / "amendment.md"
    output = tmp_path / "cleaned.md"
    source.write_text(
        "Cover page\n"
        + "\n".join(_hindi_line() for _ in range(6))
        + "\n"
        "New Delhi, the 29th  January , 2019\n"
        "F. No. 02-01/Enf-1(1)/FSSAI-2012.- Whereas the draft of certain regulations\n"
        "Amendment body\n",
        encoding="utf-8",
    )

    cleanup_amendment(source, output)

    cleaned = output.read_text(encoding="utf-8")
    assert cleaned.startswith("New Delhi, the 29th  January , 2019")
    assert "Amendment body" in cleaned
    assert not re.search(r"[\u0900-\u097F]", cleaned)


def test_cleanup_handles_header_merged_into_hindi_line(tmp_path):
    # Docling merges a Hindi fragment with the English authority/date line
    # (files 28/29 shape). The mixed line is kept, but the Hindi-only lines go.
    source = tmp_path / "amendment.md"
    output = tmp_path / "cleaned.md"
    source.write_text(
        "Cover page\n"
        + "\n".join(_hindi_line() for _ in range(5))
        + "\n"
        "फा. सं. मानक/एम एंड एमपी/ 2018। MINISTRY OF HEALTH AND FAMILY WELFARE "
        "(FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA) NOTIFICATION New Delhi, the 29th January, 2019.\n"
        "And whereas the copies of the said official Gazette were made available.\n"
        "Amendment body\n",
        encoding="utf-8",
    )

    cleanup_amendment(source, output)

    cleaned = output.read_text(encoding="utf-8")
    assert "MINISTRY OF HEALTH AND FAMILY WELFARE" in cleaned
    assert "Amendment body" in cleaned
    assert cleaned.count("\n".join([_hindi_line()])) == 0  # no Hindi-only line survives


def test_cleanup_removes_trailing_hindi_block(tmp_path):
    source = tmp_path / "amendment.md"
    output = tmp_path / "cleaned.md"
    source.write_text(
        "## FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA NOTIFICATION\n"
        "\n"
        "New Delhi, the 1st January, 2025\n"
        "\n"
        "Amendment body line one\n"
        "Amendment body line two\n"
        + "\n".join(_hindi_line() for _ in range(4))
        + "\n",
        encoding="utf-8",
    )

    cleanup_amendment(source, output)

    cleaned = output.read_text(encoding="utf-8")
    assert cleaned.startswith("## FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA NOTIFICATION")
    assert "Amendment body line two" in cleaned
    assert _hindi_line() not in cleaned
    assert not re.search(r"[\u0900-\u097F]", cleaned)


def test_cleanup_never_empties_a_devanagari_only_document(tmp_path):
    source = tmp_path / "amendment.md"
    output = tmp_path / "cleaned.md"
    source.write_text("\n".join(_hindi_line() for _ in range(8)) + "\n", encoding="utf-8")

    cleanup_amendment(source, output)

    assert output.read_text(encoding="utf-8").strip()


def test_cleanup_regulation_cuts_leading_hindi_block(tmp_path):
    source = tmp_path / "Regulation.md"
    output = tmp_path / "cleaned.md"
    source.write_text(
        "vlk/kj.k\n"
        "Hkkx III[k.M 4\n"
        + "\n".join(_hindi_line() for _ in range(5))
        + "\n"
        "## MINISTRY OF HEALTH AND FAMILY WELFARE\n"
        "\n"
        "(FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA)\n"
        "\n"
        "## NOTIFICATION\n"
        "\n"
        "New Delhi, the 29th December, 2017\n"
        "\n"
        "1. Short title and commencement.- These regulations may be called the Organic Foods Regulations\n",
        encoding="utf-8",
    )

    cleanup_regulation(source, output)

    cleaned = output.read_text(encoding="utf-8")
    assert cleaned.startswith("## MINISTRY OF HEALTH AND FAMILY WELFARE")
    assert "Short title and commencement" in cleaned
    assert "Hkkx" not in cleaned  # legacy-font Hindi header is cut with the block
    assert not re.search(r"[\u0900-\u097F]", cleaned)


def test_cleanup_regulation_leaves_english_only_document_untouched(tmp_path):
    # The Ministry heading also appears in already-English compendia; nothing may
    # be dropped because there is no Devanagari before it.
    source = tmp_path / "Regulation.md"
    output = tmp_path / "cleaned.md"
    source.write_text(
        "## 1.1: Title and commencement\n"
        "\n"
        "- 1.1.1:These regulations may be called the Food Safety and Standards Regulations\n"
        "\n"
        "## MINISTRY OF HEALTH AND FAMILY WELFARE\n"
        "\n"
        "## NOTIFICATION\n"
        "\n"
        "F.No. 2-15015/30/2010 Whereas in exercise of the powers conferred\n",
        encoding="utf-8",
    )

    cleanup_regulation(source, output)

    cleaned = output.read_text(encoding="utf-8")
    assert cleaned.startswith("## 1.1: Title and commencement")
    assert "1.1.1:These regulations may be called" in cleaned


def test_cleanup_regulation_drops_trailing_devanagari_line(tmp_path):
    source = tmp_path / "Regulation.md"
    output = tmp_path / "cleaned.md"
    source.write_text(
        "\n".join(_hindi_line() for _ in range(4))
        + "\n"
        "## MINISTRY OF HEALTH AND FAMILY WELFARE\n"
        "\n"
        "## NOTIFICATION\n"
        "\n"
        "English body line one\n"
        "English body line two\n"
        + _hindi_line()
        + "\n",
        encoding="utf-8",
    )

    cleanup_regulation(source, output)

    cleaned = output.read_text(encoding="utf-8")
    assert cleaned.startswith("## MINISTRY OF HEALTH AND FAMILY WELFARE")
    assert "English body line two" in cleaned
    assert not re.search(r"[\u0900-\u097F]", cleaned)


def test_cleanup_regulation_never_empties_devanagari_only_document(tmp_path):
    source = tmp_path / "Regulation.md"
    output = tmp_path / "cleaned.md"
    source.write_text("\n".join(_hindi_line() for _ in range(8)) + "\n", encoding="utf-8")

    cleanup_regulation(source, output)

    assert output.read_text(encoding="utf-8").strip()