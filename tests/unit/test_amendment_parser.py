import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from pre_processing.amendment_parser import AmendmentItem, AmendmentList, parse_amendment
from pre_processing.config import PreprocessingConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
SAMPLE_MD = FIXTURES_DIR / "01_273797.cleaned.md"


def _fake_llm(result: AmendmentList) -> MagicMock:
    fake = MagicMock()
    fake.with_structured_output.return_value = fake
    fake.invoke.return_value = result
    return fake


def test_parse_amendment_writes_json(tmp_path):
    output = tmp_path / "amendment.json"
    result = AmendmentList(
        date="2026-06-23",
        changes=[
            AmendmentItem(schedule="2", annexure="3", amendment_text="text one"),
            AmendmentItem(schedule="4", amendment_text="text two"),
        ],
    )
    with patch("pre_processing.amendment_parser.ChatOpenAI", return_value=_fake_llm(result)):
        changes = parse_amendment(SAMPLE_MD, output)

    assert len(changes) == 2
    assert changes[0].schedule == "2"

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["date"] == "2026-06-23"
    assert data["changes"][0]["schedule"] == "2"
    assert data["changes"][1]["amendment_text"] == "text two"


def test_parse_amendment_default_output_path(tmp_path):
    md_copy = tmp_path / "01_273797.cleaned.md"
    md_copy.write_text(SAMPLE_MD.read_text(encoding="utf-8"), encoding="utf-8")
    result = AmendmentList(date="2026-06-23", changes=[])
    with patch("pre_processing.amendment_parser.ChatOpenAI", return_value=_fake_llm(result)):
        parse_amendment(md_copy)

    assert (tmp_path / "01_273797.cleaned.json").exists()


def test_parse_amendment_invokes_with_document(tmp_path):
    output = tmp_path / "amendment.json"
    result = AmendmentList(date="2026-06-23", changes=[])
    fake = _fake_llm(result)
    with patch("pre_processing.amendment_parser.ChatOpenAI", return_value=fake):
        parse_amendment(SAMPLE_MD, output)

    assert fake.invoke.called
    messages = fake.invoke.call_args[0][0]
    assert len(messages) == 2
    assert SAMPLE_MD.read_text(encoding="utf-8") in messages[1].content


def test_parse_amendment_uses_injected_config(tmp_path):
    output = tmp_path / "amendment.json"
    result = AmendmentList(date="2026-06-23", changes=[])
    config = PreprocessingConfig(
        amendment_parser_model="test/parser",
        amendment_parser_max_tokens=123,
    )
    with patch("pre_processing.amendment_parser.ChatOpenAI", return_value=_fake_llm(result)) as chat:
        parse_amendment(SAMPLE_MD, output, config=config)

    assert chat.call_args.kwargs["model"] == "test/parser"
    assert chat.call_args.kwargs["max_tokens"] == 123


def test_amendment_item_optional_fields():
    item = AmendmentItem(amendment_text="x")
    assert item.regulation is None
    assert item.subregulation is None
    assert item.schedule is None

    schedule_item = AmendmentItem(schedule="2", annexure="3", amendment_text="x")
    assert schedule_item.schedule == "2"
    assert schedule_item.regulation is None
