import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pre_processing import apply_amendment as module
from pre_processing.amendment_parser import AmendmentItem
from pre_processing.apply_amendment import apply_amendment, apply_amendments
from pre_processing.regulation_parser import Regulation

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
REGULATION_JSON = FIXTURES_DIR / "regulation.json"
AMENDMENTS_DIR = FIXTURES_DIR


def _regulation() -> Regulation:
    return Regulation.model_validate_json(REGULATION_JSON.read_text(encoding="utf-8"))


def test_find_target_annexure():
    regulation = _regulation()
    change = AmendmentItem(schedule="2", annexure="3", amendment_text="x")
    kind, item = module._find_target(regulation, change)
    assert kind == "update"
    assert item.name == "Annexure-3"


def test_find_target_whole_schedule():
    regulation = _regulation()
    change = AmendmentItem(schedule="4", amendment_text="x")
    kind, item = module._find_target(regulation, change)
    assert kind == "update"
    assert item.name == "Schedule 4"


def test_find_target_subregulation_update():
    regulation = _regulation()
    change = AmendmentItem(regulation="1.2", subregulation="1.2.1", amendment_text="x")
    kind, item = module._find_target(regulation, change)
    assert kind == "update"
    assert item.no == "1.2.1"


def test_find_target_subregulation_insert():
    regulation = _regulation()
    change = AmendmentItem(regulation="2.1", subregulation="2.1.17", amendment_text="x")
    kind, section, no = module._find_target(regulation, change)
    assert kind == "insert"
    assert section.no == "2.1"
    assert no == "2.1.17"


def test_find_target_no_match():
    regulation = _regulation()
    change = AmendmentItem(regulation="9.9", subregulation="9.9.9", amendment_text="x")
    assert module._find_target(regulation, change) is None


def test_apply_schedule_paragraph_amendment_preserves_surrounding_text():
    current = """1.1 First paragraph
5.2.4 Previous paragraph
5.2.5 Old storage requirement.
5.2.6 Following paragraph
9.1 Another section"""
    amendment = (
        "in Schedule 4, for paragraph 5.2.5, the following shall be substituted, namely:- "
        '“5.2.5 New storage requirement.”'
    )

    updated = module._apply_schedule_amendment(current, amendment)

    assert updated == """1.1 First paragraph
5.2.4 Previous paragraph
5.2.5 New storage requirement.
5.2.6 Following paragraph
9.1 Another section"""


def test_apply_schedule_clause_insertion_preserves_surrounding_text():
    current = """6. Other heading
(1) First clause.
7. Fried Foods
(1) Good oil.
(4) Re-heating and reuse of oil should be avoided.
8. Next heading"""
    amendment = (
        "in Schedule 4, in Part-V, in paragraph VI, in sub-paragraph 7 relating to Fried Foods, "
        'in clause (4), the following word and figure shall be inserted, namely— “However, oil shall not be reused.”'
    )

    updated = module._apply_schedule_amendment(current, amendment)

    assert "(4) Re-heating and reuse of oil should be avoided. However, oil shall not be reused." in updated
    assert "6. Other heading" in updated
    assert "8. Next heading" in updated


def test_apply_schedule_amendment_writes_json(tmp_path):
    amendment_json = AMENDMENTS_DIR / "01_273797.json"
    output = tmp_path / "Regulation.final.json"
    with (
        patch("pre_processing.apply_amendment.ChatOpenAI"),
        patch("pre_processing.apply_amendment._llm_apply", return_value="UPDATED-TEXT"),
    ):
        result = apply_amendment(REGULATION_JSON, amendment_json, output)

    annexure_3 = next(
        a for s in result.schedules if s.name == "Schedule 2" for a in s.annexures if a.name == "Annexure-3"
    )
    schedule_4 = next(s for s in result.schedules if s.name == "Schedule 4")
    assert annexure_3.text == "UPDATED-TEXT"
    assert schedule_4.text == "UPDATED-TEXT"

    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert len(data["schedules"]) == 4


def test_apply_subregulation_and_insert(tmp_path):
    amendment_json = AMENDMENTS_DIR / "02_1_Notification.json"
    output = tmp_path / "Regulation.final.json"
    with (
        patch("pre_processing.apply_amendment.ChatOpenAI"),
        patch("pre_processing.apply_amendment._llm_apply", return_value="UPDATED-TEXT"),
    ):
        result = apply_amendment(REGULATION_JSON, amendment_json, output)

    section_21 = next(s for ch in result.chapters for s in ch.sections if s.no == "2.1")
    inserted = next(ss for ss in section_21.sub_sections if ss.no == "2.1.17")
    assert inserted.text == "UPDATED-TEXT"

    sub_121 = next(
        ss for ch in result.chapters for s in ch.sections if s.no == "1.2" for ss in s.sub_sections if ss.no == "1.2.1"
    )
    assert sub_121.text == "UPDATED-TEXT"

    assert output.exists()


def test_default_output_path_naming(tmp_path):
    regulation_copy = tmp_path / "Regulation.cleaned.json"
    regulation_copy.write_text(REGULATION_JSON.read_text(encoding="utf-8"), encoding="utf-8")
    amendment_json = AMENDMENTS_DIR / "03_Quality_Vegetable_Oil.json"
    with (
        patch("pre_processing.apply_amendment.ChatOpenAI"),
        patch("pre_processing.apply_amendment._llm_apply", return_value="UPDATED-TEXT"),
    ):
        apply_amendment(regulation_copy, amendment_json)
    assert (tmp_path / "Regulation.final.json").exists()


def test_apply_amendments_writes_output(tmp_path):
    output = tmp_path / "Regulation.final.json"
    amendments = [
        AMENDMENTS_DIR / "03_Quality_Vegetable_Oil.json",
        AMENDMENTS_DIR / "02_1_Notification.json",
        AMENDMENTS_DIR / "01_273797.json",
    ]
    with (
        patch("pre_processing.apply_amendment.ChatOpenAI"),
        patch("pre_processing.apply_amendment._llm_apply", return_value="UPDATED-TEXT"),
    ):
        result = apply_amendments(REGULATION_JSON, amendments, output)

    section_21 = next(s for ch in result.chapters for s in ch.sections if s.no == "2.1")
    assert any(ss.no == "2.1.17" for ss in section_21.sub_sections)
    annexure_3 = next(
        a for s in result.schedules if s.name == "Schedule 2" for a in s.annexures if a.name == "Annexure-3"
    )
    assert annexure_3.text == "UPDATED-TEXT"
    assert output.exists()


def test_apply_amendments_applies_in_date_order(tmp_path):
    amendment_a = tmp_path / "A.json"
    amendment_b = tmp_path / "B.json"
    amendment_a.write_text(
        json.dumps(
            {"date": "2020-01-01", "changes": [{"regulation": "1.2", "subregulation": "1.2.1", "amendment_text": "first"}]}
        ),
        encoding="utf-8",
    )
    amendment_b.write_text(
        json.dumps(
            {"date": "2025-01-01", "changes": [{"regulation": "1.2", "subregulation": "1.2.1", "amendment_text": "second"}]}
        ),
        encoding="utf-8",
    )

    applied = []
    original = module.apply_amendment_to_regulation
    try:
        def recording(regulation, amendment, llm=None, model=module.DEFAULT_MODEL, config=None):
            applied.append(amendment.date)
            return regulation

        module.apply_amendment_to_regulation = recording
        with patch("pre_processing.apply_amendment.ChatOpenAI"):
            apply_amendments(REGULATION_JSON, [amendment_b, amendment_a])
    finally:
        module.apply_amendment_to_regulation = original

    assert applied == ["2020-01-01", "2025-01-01"]
