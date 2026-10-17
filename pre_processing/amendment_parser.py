#!/usr/bin/env python3
"""Extract amendments from a regulation amendment Markdown file using LangChain."""

import json
import os
import re
from pathlib import Path
from typing import Optional

import openai
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError
import tiktoken

from prompts.parse_amendment_prompt import PARSE_AMENDMENT
from pre_processing.config import DEFAULT_CONFIG, PreprocessingConfig
from pre_processing.retry import invoke_with_retry


class AmendmentItem(BaseModel):
    regulation: Optional[str] = None
    subregulation: Optional[str] = None
    schedule: Optional[str] = None
    annexure: Optional[str] = None
    form: Optional[str] = None
    amendment_text: str


class AmendmentList(BaseModel):
    date: str
    changes: list[AmendmentItem] = Field(default_factory=list)


DEFAULT_MODEL = DEFAULT_CONFIG.amendment_parser_model

load_dotenv()

_encoding = tiktoken.get_encoding("cl100k_base")

# Breakpoints are the starts of complete amendment blocks only: top-level
# clause headers ("2. In the Food Safety and Standards ...", "1. Short title...")
# and change items ("(1) in regulation ...", "- (a) in ..."). A block is never
# split, so each amendment's text stays in one chunk.
_TOP_LEVEL_MARKER_RE = re.compile(
    r"(?m)^[ \t]*\d+\.\s+(?:In\s+the\s+Food\s+Safety|Short\s+title|\(\d+\)\s+These\s+regulations|\([A-Z]\)\s+(?:for|in)|These\s+regulations)",
    re.IGNORECASE,
)
_CHANGE_ITEM_MARKER_RE = re.compile(r"(?m)^[ \t]*-?[ \t]*(?:\(\d+\)|\([a-z]\))[ \t]+(?=(?:in|In)\b)")

_SEMANTIC_MARKERS: list[re.Pattern] = [
    _TOP_LEVEL_MARKER_RE,
    _CHANGE_ITEM_MARKER_RE,
]


def _marker_spans(document: str, patterns: list[re.Pattern]) -> list[tuple[int, int]]:
    """Return (start, end) of every marker match, in document order."""
    spans: list[tuple[int, int]] = []
    for pattern in patterns:
        spans.extend((match.start(), match.end()) for match in pattern.finditer(document))
    spans.sort(key=lambda pair: pair[0])
    return spans


def _force_split_oversized(text: str, max_tokens: int) -> list[str]:
    """Split ``text`` into pieces under ``max_tokens``, preferring natural breaks.

    Used only as a last resort for a single amendment block that is itself larger
    than the budget (e.g. a huge schedule table): keeping it whole would exceed the
    model context entirely. Tries paragraph, then line, then sentence boundaries,
    falling back to hard token windows.
    """
    if len(_encoding.encode(text)) <= max_tokens:
        return [text]

    for separator in ("\n\n", "\n", ". "):
        parts = text.split(separator)
        if len(parts) == 1:
            continue
        pieces: list[str] = []
        current = ""
        for part in parts:
            candidate = part if not current else current + separator + part
            if current and len(_encoding.encode(candidate)) > max_tokens:
                pieces.append(current)
                current = part
            else:
                current = candidate
        if current:
            pieces.append(current)
        if all(len(_encoding.encode(piece)) <= max_tokens for piece in pieces):
            return pieces

    tokens = _encoding.encode(text)
    return [
        _encoding.decode(tokens[start : start + max_tokens])
        for start in range(0, len(tokens), max_tokens)
    ]


def _split_amendment_document(
    document: str,
    max_tokens: int,
    hard_max_tokens: int | None = None,
) -> list[str]:
    """Group complete amendment blocks into chunks under ``max_tokens``.

    Splits only at amendment-block boundaries, so one amendment's text never
    spans two chunks. The notification prefix is repeated in every chunk so each
    piece is self-contained. A single block larger than ``max_tokens`` keeps its
    own chunk intact rather than being cut mid-amendment, unless it also exceeds
    ``hard_max_tokens`` (then it is force-split, since it cannot be sent whole).
    """
    if len(_encoding.encode(document)) <= max_tokens:
        return [document]
    spans = _marker_spans(document, _SEMANTIC_MARKERS)
    if not spans:
        chunks = [document]
        return _force_split_all(chunks, hard_max_tokens)

    prefix = document[: spans[0][0]]
    prefix_tokens = len(_encoding.encode(prefix))
    raw_blocks = [
        document[spans[i][0] : spans[i + 1][0] if i + 1 < len(spans) else len(document)]
        for i in range(len(spans))
    ]
    block_tokens = [len(_encoding.encode(block)) for block in raw_blocks]

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = prefix_tokens
    for block, tokens in zip(raw_blocks, block_tokens):
        if current and current_tokens + tokens > max_tokens:
            chunks.append(prefix + "".join(current))
            current = []
            current_tokens = prefix_tokens
        current.append(block)
        current_tokens += tokens
    if current:
        chunks.append(prefix + "".join(current))
    return _force_split_all(chunks or [document], hard_max_tokens)


def _force_split_all(chunks: list[str], hard_max_tokens: int | None) -> list[str]:
    """Force-split any chunk still exceeding the hard ceiling."""
    if hard_max_tokens is None:
        return chunks
    result: list[str] = []
    for chunk in chunks:
        if len(_encoding.encode(chunk)) > hard_max_tokens:
            result.extend(_force_split_oversized(chunk, hard_max_tokens))
        else:
            result.append(chunk)
    return result


def _source_amendment_blocks(document: str) -> list[str]:
    """Split a notification into source blocks at amendment markers."""
    spans = _marker_spans(document, _SEMANTIC_MARKERS)
    if not spans:
        return [document.strip()] if document.strip() else []
    return [
        document[spans[i][0] : spans[i + 1][0] if i + 1 < len(spans) else len(document)].strip()
        for i in range(len(spans))
    ]


def _change_target_matches(change: AmendmentItem, block: str) -> bool:
    normalized = block.casefold()
    if change.subregulation:
        if not re.search(
            rf"sub[- ]?regulation\s+{re.escape(change.subregulation)}\b",
            normalized,
        ):
            return False
    if change.regulation:
        if f"regulation {change.regulation}" not in normalized:
            return False
    if change.schedule:
        if f"schedule {change.schedule}" not in normalized:
            return False
    return True


def _restore_truncated_text(changes: list[AmendmentItem], document: str) -> None:
    """Replace model ellipses with the complete matching source amendment block."""
    blocks = _source_amendment_blocks(document)
    for change in changes:
        if not re.search(r"(?:…|\.\.\.)", change.amendment_text):
            continue
        if not (change.subregulation or change.regulation or change.schedule):
            continue
        match = next(
            (block for block in blocks if _change_target_matches(change, block)),
            None,
        )
        if match:
            change.amendment_text = re.sub(
                r"^(?:\(\d+\)|\([a-z]\))[ \t]+",
                "",
                match,
                count=1,
                flags=re.IGNORECASE,
            ).strip()


def _normalize_change_targets(changes: list[AmendmentItem]) -> None:
    """Fill the parent regulation when a model returns only a sub-regulation."""
    for change in changes:
        if change.regulation or not change.subregulation:
            continue
        match = re.match(r"^(\d+\.\d+)\.\d+$", change.subregulation)
        if match:
            change.regulation = match.group(1)


_JSON_ONLY_INSTRUCTION = (
    "Respond with a single JSON object and nothing else: no prose, no markdown "
    "code fences, and no explanation. The object must match the schema shown above."
)


def _strip_json_fences(text: str) -> str:
    """Remove a surrounding markdown code fence from a JSON response."""
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL | re.IGNORECASE)
    return fence.group(1).strip() if fence else stripped


def _invoke_plain_json(base_llm, part: str, config: PreprocessingConfig) -> AmendmentList:
    """Ask for plain JSON (no tool calling) and validate it with the schema."""
    messages = [
        SystemMessage(content=f"{PARSE_AMENDMENT}\n\n{_JSON_ONLY_INSTRUCTION}"),
        HumanMessage(content=part),
    ]
    last_error: Exception | None = None
    for _ in range(config.llm_max_retries + 1):
        response = invoke_with_retry(
            base_llm,
            messages,
            max_retries=config.llm_max_retries,
            base_delay=config.llm_retry_base_delay,
        )
        content = response.content if isinstance(response.content, str) else str(response.content)
        try:
            return AmendmentList.model_validate_json(_strip_json_fences(content))
        except ValidationError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _invoke_amendment(
    part: str,
    base_llm,
    structured_llm,
    config: PreprocessingConfig,
) -> AmendmentList:
    """Parse one document chunk, preferring structured output.

    Tool-calling structured output occasionally runs to the completion cap
    (``LengthFinishReasonError``) without producing a usable result. When that
    happens, fall back to asking for plain JSON and validating it with the same
    pydantic model.
    """
    messages = [SystemMessage(content=PARSE_AMENDMENT), HumanMessage(content=part)]
    try:
        return invoke_with_retry(
            structured_llm,
            messages,
            max_retries=config.llm_max_retries,
            base_delay=config.llm_retry_base_delay,
        )
    except openai.LengthFinishReasonError:
        return _invoke_plain_json(base_llm, part, config)


def parse_amendment(
    md_path: str | Path,
    output_json_path: str | Path | None = None,
    model: str | None = None,
    config: PreprocessingConfig = DEFAULT_CONFIG,
) -> list[AmendmentItem]:
    """Extract amendments from an amendment Markdown file.

    When ``output_json_path`` is not given, the JSON is written next to the
    input file with a ``.json`` suffix.
    """
    output_path = Path(output_json_path) if output_json_path else Path(md_path).with_suffix(".json")
    document = Path(md_path).read_text(encoding="utf-8")
    llm_kwargs: dict = {
        "model": model or config.amendment_parser_model,
        "base_url": config.base_url,
        "api_key": os.environ[config.api_key_env],
        "temperature": config.temperature,
        "max_tokens": config.amendment_parser_max_tokens,
        "extra_body": {
            "provider": {
                "order": list(config.provider_order),
                "allow_fallbacks": config.allow_provider_fallbacks,
                "require_parameters": config.require_provider_parameters,
            }
        },
    }
    if config.amendment_parser_reasoning_effort is not None:
        llm_kwargs["reasoning_effort"] = config.amendment_parser_reasoning_effort
    base_llm = ChatOpenAI(**llm_kwargs)
    structured_llm = base_llm.with_structured_output(AmendmentList)

    parsed_documents = _split_amendment_document(
        document,
        config.amendment_parser_chunk_tokens,
        hard_max_tokens=config.amendment_parser_hard_chunk_tokens,
    )
    parsed_results = [
        _invoke_amendment(part, base_llm, structured_llm, config)
        for part in parsed_documents
    ]
    changes: list[AmendmentItem] = []
    for result, part in zip(parsed_results, parsed_documents):
        _normalize_change_targets(result.changes)
        _restore_truncated_text(result.changes, part)
        changes.extend(result.changes)
    result = AmendmentList(
        date=next((parsed.date for parsed in parsed_results if parsed.date), ""),
        changes=changes,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result.changes
