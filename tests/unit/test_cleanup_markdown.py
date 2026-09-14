from pre_processing.cleanup_markdown import cleanup_amendment


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