"""Integration tests that call the real LLM to assess amendment accuracy.

These are marked ``integration`` and are excluded from the default test run
(``addopts = -m "not integration"`` in ``pyproject.toml``). Run them explicitly with::

    uv run pytest -m integration -s

They require ``OPENROUTER_API_KEY`` in the environment (or ``.env``).
"""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from pre_processing.apply_amendment import apply_amendment
from pre_processing.config import DEFAULT_CONFIG

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
REGULATION_JSON = FIXTURES_DIR / "regulation.json"
TEST_CONFIG = replace(
    DEFAULT_CONFIG,
    base_url="https://openrouter.ai/api/v1",
    api_key_env="OPENROUTER_API_KEY",
    amendment_applier_model="openai/gpt-oss-120b",
    amendment_applier_max_tokens=4_096,
    max_amendment_workers=1,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY not set"),
]


def _run(amendment_name: str, tmp_path: Path):
    amendment_json = FIXTURES_DIR / amendment_name
    output = tmp_path / "Regulation.final.json"
    result = apply_amendment(REGULATION_JSON, amendment_json, output, config=TEST_CONFIG)
    assert output.exists()
    return result


def test_llm_apply_schedule_amendment(tmp_path):
    result = _run("01_273797.json", tmp_path)

    annexure_3 = next(
        a for s in result.schedules if s.name == "Schedule 2" for a in s.annexures if a.name == "Annexure-3"
    )
    schedule_4 = next(s for s in result.schedules if s.name == "Schedule 4")

    assert "daily records of production" in annexure_3.text.lower()
    assert "First in First out" in schedule_4.text
    print("\n=== Annexure-3 updated text ===\n", annexure_3.text)
    print("\n=== Schedule 4 updated text ===\n", schedule_4.text)


def test_llm_apply_subregulation_and_insert(tmp_path):
    result = _run("02_1_Notification.json", tmp_path)

    section_21 = next(s for ch in result.chapters for s in ch.sections if s.no == "2.1")
    inserted = next(ss for ss in section_21.sub_sections if ss.no == "2.1.17")
    sub_121 = next(
        ss for ch in result.chapters for s in ch.sections if s.no == "1.2" for ss in s.sub_sections if ss.no == "1.2.1"
    )
    sub_211 = next(ss for ss in section_21.sub_sections if ss.no == "2.1.1")
    sub_217 = next(ss for ss in section_21.sub_sections if ss.no == "2.1.7")

    assert "petty food business operator" in sub_121.text.lower()
    assert "Inspection and audit" in inserted.text
    assert "street food vendors" in sub_211.text.lower()
    assert "Validity of Registration and License" in sub_217.text
    print("\n=== 1.2.1 updated text ===\n", sub_121.text)
    print("\n=== 2.1.17 inserted text ===\n", inserted.text)
    print("\n=== 2.1.1 updated text ===\n", sub_211.text)
    print("\n=== 2.1.7 updated text ===\n", sub_217.text)
