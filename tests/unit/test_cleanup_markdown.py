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
