"""Integration test for LLM-based amendment extraction."""

import json
import os
import re
from dataclasses import replace
from pathlib import Path

import pytest

from pre_processing.amendment_parser import AmendmentList, parse_amendment
from pre_processing.config import DEFAULT_CONFIG

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
SOURCE_MARKDOWN = FIXTURES_DIR / "01_273797.cleaned.md"
EXPECTED_JSON = FIXTURES_DIR / "01_273797.json"
TEST_CONFIG = replace(
    DEFAULT_CONFIG,
    base_url="https://openrouter.ai/api/v1",
    api_key_env="OPENROUTER_API_KEY",
    amendment_parser_model="openai/gpt-oss-120b",
    amendment_parser_max_tokens=4_096,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY not set"),
]


def _normalized(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"namely\s*:\s*-", "namely:", value, flags=re.IGNORECASE)
    value = re.sub(r";\s*$", "", value)
    return value.casefold()


def _normalized_changes(dataset: AmendmentList) -> list[dict[str, str | None]]:
    return [
        {
            "regulation": change.regulation or None,
            "subregulation": change.subregulation or None,
            "schedule": change.schedule or None,
            "annexure": change.annexure or None,
            "form": change.form or None,
            "amendment_text": _normalized(change.amendment_text),
        }
        for change in dataset.changes
    ]


def test_llm_parse_amendment_matches_golden(tmp_path):
    output = tmp_path / "01_273797.json"
    parse_amendment(SOURCE_MARKDOWN, output, config=TEST_CONFIG)

    actual = AmendmentList.model_validate_json(output.read_text(encoding="utf-8"))
    expected = AmendmentList.model_validate(
        json.loads(EXPECTED_JSON.read_text(encoding="utf-8"))
    )

    assert actual.date == expected.date
    assert _normalized_changes(actual) == _normalized_changes(expected)
