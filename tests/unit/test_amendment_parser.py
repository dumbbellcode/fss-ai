import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import openai
import tiktoken

from pre_processing.amendment_parser import (
    AmendmentItem,
    AmendmentList,
    _CHANGE_ITEM_MARKER_RE,
    _SUBREGULATION_MARKER_RE,
    _TOP_LEVEL_MARKER_RE,
    _has_change_instructions,
    _has_elision,
    _invoke_amendment,
    _marker_spans,
    _provider_extra_body,
    _restore_truncated_text,
    _result_is_degenerate,
    _SEMANTIC_MARKERS,
    _split_amendment_document,
    _strip_json_fences,
    parse_amendment,
)
from pre_processing.config import PreprocessingConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
SAMPLE_MD = FIXTURES_DIR / "01_273797.cleaned.md"


def _fake_llm(result: AmendmentList) -> MagicMock:
    fake = MagicMock()
    fake.with_structured_output.return_value = fake
    fake.invoke.return_value = result
    return fake


def _sample_result() -> AmendmentList:
    """A non-degenerate result so the structured path is used for SAMPLE_MD."""
    return AmendmentList(
        date="2026-06-23",
        changes=[AmendmentItem(amendment_text="in regulation 1.1, the word old shall be omitted")],
    )


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
    result = _sample_result()
    with patch("pre_processing.amendment_parser.ChatOpenAI", return_value=_fake_llm(result)):
        parse_amendment(md_copy)

    assert (tmp_path / "01_273797.cleaned.json").exists()


def test_parse_amendment_invokes_with_document(tmp_path):
    output = tmp_path / "amendment.json"
    result = _sample_result()
    fake = _fake_llm(result)
    with patch("pre_processing.amendment_parser.ChatOpenAI", return_value=fake):
        parse_amendment(SAMPLE_MD, output)

    assert fake.invoke.called
    messages = fake.invoke.call_args[0][0]
    assert len(messages) == 2
    assert SAMPLE_MD.read_text(encoding="utf-8") in messages[1].content


def test_parse_amendment_uses_injected_config(tmp_path):
    output = tmp_path / "amendment.json"
    result = _sample_result()
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


def test_restore_truncated_amendment_text_from_source_block():
    change = AmendmentItem(
        regulation="2.2",
        subregulation="2.2.7",
        amendment_text="in sub-regulation 2.2.7, the following entries shall be substituted, namely:…",
    )
    document = (
        "(d) in sub-regulation 2.2.7, the following entries shall be substituted, namely:-\n"
        "| Parameter | Value |\n| --- | --- |\n| Virgin olive oil | 0.03 |\n"
        "(e) in sub-regulation 2.2.9, another amendment.\n"
    )

    _restore_truncated_text([change], document)

    assert "Virgin olive oil" in change.amendment_text
    assert "…" not in change.amendment_text

def test_split_amendment_document_packs_multiple_markers():
    encoding = tiktoken.get_encoding("cl100k_base")
    prefix = "NOTIFICATION\nNew Delhi, the 1st January, 2025\n"
    blocks = [
        "(1) in regulation 1.1, the word “old” shall be omitted;\n",
        "(2) in regulation 1.2, the word “older” shall be omitted;\n",
        "(3) in regulation 1.3, the word “oldest” shall be omitted;\n",
    ]
    document = prefix + "".join(blocks)
    max_tokens = len(encoding.encode(prefix + blocks[0] + blocks[1]))

    chunks = _split_amendment_document(document, max_tokens)

    assert chunks == [prefix + blocks[0] + blocks[1], prefix + blocks[2]]

def test_split_amendment_document_keeps_large_budget_in_one_chunk():
    prefix = "NOTIFICATION\nNew Delhi, the 1st January, 2025\n"
    document = prefix + (
        "(1) in regulation 1.1, the word “old” shall be omitted;\n"
        "(2) in regulation 1.2, the word “older” shall be omitted;\n"
    )

    assert _split_amendment_document(document, 30_000) == [document]


def test_split_keeps_oversized_block_whole_without_hard_ceiling():
    encoding = tiktoken.get_encoding("cl100k_base")
    document = "\n".join(["a plain sentence with no amendment markers"] * 200)

    chunks = _split_amendment_document(document, 50)

    assert chunks == [document]
    assert len(encoding.encode(chunks[0])) > 50


def test_split_force_splits_oversized_block_when_hard_ceiling_set():
    encoding = tiktoken.get_encoding("cl100k_base")
    document = "\n".join(["a plain sentence with no amendment markers"] * 200)

    chunks = _split_amendment_document(document, 50, hard_max_tokens=50)

    assert len(chunks) > 1
    assert all(len(encoding.encode(chunk)) <= 50 for chunk in chunks)


def test_strip_json_fences_unwraps_code_block():
    assert _strip_json_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_json_fences('```\n{"a": 1}\n```') == '{"a": 1}'
    assert _strip_json_fences('{"a": 1}') == '{"a": 1}'


def test_top_level_marker_ignores_lettered_sub_items():
    # In-list sub-items like "2. (a) in raw form" are NOT amendment boundaries.
    assert not _TOP_LEVEL_MARKER_RE.search("2. (a) in raw form, is dried gummy exudation;\n")
    assert not _TOP_LEVEL_MARKER_RE.search("4. (c) in un-ground form, is flattened;\n")
    assert not _TOP_LEVEL_MARKER_RE.search("5. (a) for food products;\n")
    # Real top-level clause headers still match.
    assert _TOP_LEVEL_MARKER_RE.search("2. In the Food Safety and Standards regulations, 2011,-\n")
    assert _TOP_LEVEL_MARKER_RE.search("1. Short  title  and  commencement.\n")


def test_change_item_marker_matches_lettered_items_and_after():
    assert _CHANGE_ITEM_MARKER_RE.search("- (A) in Chapter 3, after regulation 3.3\n")
    assert _CHANGE_ITEM_MARKER_RE.search("(B) after APPENDIX B, the following shall be inserted\n")
    assert _CHANGE_ITEM_MARKER_RE.search("- (a) in regulation 2.2\n")
    # "insert" must not be mistaken for the "in" lead-in.
    assert not _CHANGE_ITEM_MARKER_RE.search("- (a) insert a new clause\n")


def test_subregulation_marker_matches_structural_headings():
    assert _SUBREGULATION_MARKER_RE.search("## '3.2.9.  Preservatives:\n")
    assert _SUBREGULATION_MARKER_RE.search("## 3.2.10 Acidity regulator\n")
    assert _SUBREGULATION_MARKER_RE.search("## 1. Sodium alginate:\n")
    assert not _SUBREGULATION_MARKER_RE.search("a plain prose line with no heading\n")


def test_marker_spans_dedupes_overlapping_starts():
    document = "2. In the Food Safety and Standards regulations, 2011,-\nnext line\n"
    spans = _marker_spans(document, _SEMANTIC_MARKERS)
    starts = [start for start, _ in spans]
    assert starts == sorted(starts)
    assert len(starts) == len(set(starts))


def test_split_keeps_one_subregulation_together_and_is_lossless():
    prefix = "## NOTIFICATION\nNew Delhi, the 1st January, 2025\n"
    body = (
        "## 6. Tragacanth gum:\n"
        "- (1) Tragacanth gum,-\n"
        "2. (a) in raw form, is dried gummy exudation;\n"
        "3. (b) in powdered form shall be in white colour;\n"
        "4. (c) in un-ground form, is flattened;\n"
        "| 11 | Arsenic, mg/kg, Max | 3.0 |\n"
        "## 7. Acacia:\n"
        "- (1) Acacia shall conform to the table below.\n"
    )
    document = prefix + body

    chunks = _split_amendment_document(document, 40)

    # Rebuild the body by dropping the repeated prefix; nothing may be lost.
    rebuilt = ""
    for chunk in chunks:
        assert chunk.startswith(prefix)
        rebuilt += chunk[len(prefix):]
    assert rebuilt == body


def test_invoke_amendment_falls_back_to_plain_json_on_length_error():
    structured = MagicMock()
    structured.invoke.side_effect = openai.LengthFinishReasonError(completion=Mock())

    base = MagicMock()
    payload = json.dumps({"date": "2016-07-13", "changes": [{"amendment_text": "x"}]})
    base.invoke.return_value = MagicMock(content=payload)

    result = _invoke_amendment("some chunk text", base, structured, PreprocessingConfig())

    assert result.date == "2016-07-13"
    assert len(result.changes) == 1
    assert result.changes[0].amendment_text == "x"
    assert base.invoke.called


def test_invoke_amendment_uses_structured_output_when_it_succeeds():
    structured = MagicMock()
    structured.invoke.return_value = AmendmentList(date="2020-01-01", changes=[])
    base = MagicMock()

    result = _invoke_amendment("chunk", base, structured, PreprocessingConfig())

    assert result.date == "2020-01-01"
    assert not base.invoke.called


def test_has_change_instructions_detects_amendment_text():
    assert _has_change_instructions("- (1) in regulation 2.2, the word X shall be omitted")
    assert _has_change_instructions("The following Schedule shall be substituted, namely:-")
    assert not _has_change_instructions("New Delhi, the 1st January, 2025")
    assert not _has_change_instructions("")


def test_result_is_degenerate_for_empty_changes_with_instructions():
    part = "- (1) in regulation 2.2, the word X shall be substituted"
    assert _result_is_degenerate(AmendmentList(date="2020-01-01", changes=[]), part)
    # An empty result for a chunk with no change instructions is legitimate.
    assert not _result_is_degenerate(AmendmentList(date="2020-01-01", changes=[]), "cover page only")


def test_result_is_degenerate_for_tiny_placeholder():
    placeholder = AmendmentList(
        date="2020-01-01",
        changes=[AmendmentItem(amendment_text="in\xa0\xa0...\xa0\xa0")],
    )
    assert _result_is_degenerate(placeholder, "anything")

    elided = AmendmentList(
        date="2020-01-01",
        changes=[AmendmentItem(amendment_text="Now, therefore, ... makes the following regulations ...")],
    )
    assert _result_is_degenerate(elided, "anything")

    real = AmendmentList(
        date="2020-01-01",
        changes=[
            AmendmentItem(
                amendment_text=(
                    "in sub-regulation 3.2.1, after clause 15, the following clauses shall be"
                    " inserted, namely:-\n'16. Beta-apo-8'-carotenal:\n- (1) Beta-apo-8'-carotenal"
                    " in crystal form shall be deep violet ...\n| Common Name | Beta-apo-8'-carotenal |"
                )
            )
        ],
    )
    # A multi-line verbatim body containing an ellipsis is not a placeholder.
    assert not _result_is_degenerate(real, "anything")


def test_has_elision_flags_short_single_line_ellipsis_only():
    assert _has_elision("Now, therefore, ... makes the following regulations")
    assert _has_elision("in\xa0\xa0...\xa0\xa0")
    assert not _has_elision("in regulation 1.1, the word old shall be omitted")
    assert not _has_elision("a\nb\n...\nlong multi-line verbatim body with a table")


def test_invoke_amendment_falls_back_when_structured_result_is_empty():
    structured = MagicMock()
    structured.invoke.return_value = AmendmentList(date="2020-01-01", changes=[])
    base = MagicMock()
    base.invoke.return_value = MagicMock(
        content=json.dumps({"date": "2020-01-01", "changes": [{"amendment_text": "recovered text"}]})
    )

    part = "- (1) in regulation 2.2, the word X shall be substituted"
    result = _invoke_amendment(part, base, structured, PreprocessingConfig())

    assert [c.amendment_text for c in result.changes] == ["recovered text"]
    assert base.invoke.called


def test_provider_extra_body_is_none_without_a_pin():
    assert _provider_extra_body(PreprocessingConfig()) is None

    pinned = PreprocessingConfig(provider_order=("coreweave",), allow_provider_fallbacks=False)
    body = _provider_extra_body(pinned)
    assert body == {
        "provider": {"order": ["coreweave"], "allow_fallbacks": False, "require_parameters": False}
    }


def test_parse_amendment_omits_reasoning_effort_by_default(tmp_path):
    output = tmp_path / "amendment.json"
    result = _sample_result()
    with patch("pre_processing.amendment_parser.ChatOpenAI", return_value=_fake_llm(result)) as chat:
        parse_amendment(SAMPLE_MD, output)

    assert "reasoning_effort" not in chat.call_args.kwargs
