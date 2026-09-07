#!/usr/bin/env python3
"""Apply amendments from an amendment JSON onto a parsed regulation JSON using LangChain."""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from pre_processing.amendment_parser import AmendmentItem, AmendmentList
from pre_processing.config import (
    AMENDMENT_APPLIER_MODEL,
    LLM_TEMPERATURE,
    MAX_AMENDMENT_WORKERS,
    OPENROUTER_BASE_URL,
)
from pre_processing.regulation_parser import Regulation, Schedule, Subsection

APPLY_AMENDMENT_PROMPT = """
You are given the current text of a section of an Indian food safety regulation, along with an amendment
instruction that must be applied to it. Apply the amendment faithfully and return the COMPLETE updated text
of the section (the whole section after the amendment, not just the changed part).

Current section text:
{current_text}

Amendment instruction:
{amendment_text}

Return only the complete updated text of the section.
"""

INSERT_AMENDMENT_PROMPT = """
You are inserting a new section into an Indian food safety regulation. Based solely on the amendment
instruction below, write the complete text of the new section exactly as specified by the amendment.

Amendment instruction:
{amendment_text}

Return only the complete text of the new section.
"""


DEFAULT_MODEL = AMENDMENT_APPLIER_MODEL
MAX_WORKERS = MAX_AMENDMENT_WORKERS

load_dotenv()


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _name_matches(name: str, key: str) -> bool:
    normalized_name = _normalize(name)
    normalized_key = _normalize(key)
    return normalized_name == normalized_key or normalized_key in normalized_name


def _find_target(regulation: Regulation, change: AmendmentItem):
    """Locate the object to amend.

    Returns ``("update", object)`` when the target exists, ``("insert", section, no)``
    when a new sub-regulation must be inserted, or ``None`` when no target matches.
    """
    regulation_no = change.regulation
    subregulation_no = change.subregulation

    if regulation_no and subregulation_no:
        for chapter in regulation.chapters:
            for section in chapter.sections:
                if section.no == regulation_no:
                    for subsection in section.sub_sections:
                        if subsection.no == subregulation_no:
                            return "update", subsection
                    return "insert", section, subregulation_no
        return None

    schedule_no = change.schedule
    if schedule_no:
        schedule_name = f"Schedule {schedule_no}"
        for schedule in regulation.schedules:
            if schedule.name == schedule_name:
                annexure = change.annexure
                if annexure:
                    for item in schedule.annexures:
                        if _name_matches(item.name, annexure):
                            return "update", item
                form = change.form
                if form:
                    for item in schedule.forms:
                        if _name_matches(item.name, form):
                            return "update", item
                return "update", schedule
    return None


# Tokens some models emit instead of real content on generation failure.
_GARBAGE_TOKENS = ["<｜end▁of▁sentence｜>", "<|end|>", "<|eot_id|>", "</s>"]


def _quoted_amendment_text(amendment_text: str) -> str | None:
    match = re.search(r'[“"](.*?)[”"]', amendment_text, re.DOTALL)
    return match.group(1).strip() if match else None


def _apply_schedule_amendment(current_text: str, amendment_text: str) -> str | None:
    """Apply common schedule paragraph/clause amendments without rewriting a schedule.

    Schedules can be much larger than an LLM's practical output budget. Gazette
    amendments identify the local paragraph or clause and provide its replacement
    text, so patch that local region while preserving the rest of the schedule.
    Returns ``None`` when the amendment shape cannot be located safely.
    """
    replacement = _quoted_amendment_text(amendment_text)
    if not replacement:
        return None

    paragraph = re.search(r"\bfor paragraph\s+([0-9]+(?:\.[0-9]+)+)\b", amendment_text, re.IGNORECASE)
    if paragraph:
        number = re.escape(paragraph.group(1))
        pattern = re.compile(rf"^\s*{number}\b.*?(?=^\s*\d+(?:\.\d+)+\b|\Z)", re.MULTILINE | re.DOTALL)
        updated, count = pattern.subn(replacement + "\n", current_text, count=1)
        return updated if count else None

    clause = re.search(r"\bin clause\s*\((\d+)\)", amendment_text, re.IGNORECASE)
    relating_to = re.search(r"relating to\s+([^,]+),\s*in clause", amendment_text, re.IGNORECASE)
    if not clause or not relating_to:
        return None

    heading = re.search(
        rf"^\s*\d+\.\s+{re.escape(relating_to.group(1).strip())}\s*$",
        current_text,
        re.IGNORECASE | re.MULTILINE,
    )
    if not heading:
        return None
    next_heading = re.search(r"^\s*\d+\.\s+\S", current_text[heading.end() :], re.MULTILINE)
    block_end = heading.end() + next_heading.start() if next_heading else len(current_text)
    block = current_text[heading.start() : block_end]

    clause_pattern = re.compile(
        rf"^\s*\({re.escape(clause.group(1))}\).*?(?=^\s*\(\d+\)|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    clause_match = clause_pattern.search(block)
    if not clause_match:
        return None
    original_clause = clause_match.group(0).rstrip()
    updated_clause = original_clause + " " + replacement
    updated_block = block[: clause_match.start()] + updated_clause + block[clause_match.end() :]
    return current_text[: heading.start()] + updated_block + current_text[block_end:]


def _llm_apply(llm, current_text: str, amendment_text: str, retries: int = 5) -> str:
    template = APPLY_AMENDMENT_PROMPT if current_text else INSERT_AMENDMENT_PROMPT
    prompt = template.format(current_text=current_text, amendment_text=amendment_text)
    # An update must return the whole section, so require a comparable length.
    min_len = max(10, int(len(current_text) * 0.3)) if current_text else 10
    for _ in range(retries):
        result = llm.invoke([SystemMessage(content=prompt)])
        text = (result.content or "").strip()
        for token in _GARBAGE_TOKENS:
            text = text.replace(token, "")
        text = text.strip()
        if len(text) >= min_len and not text.startswith("The current section text is not provided"):
            return text
    # All attempts failed: preserve the existing text rather than losing data.
    return current_text


def _process_group(llm, group: list) -> None:
    """Apply a group of changes targeting the same object, sequentially."""
    for change, target in group:
        started = time.perf_counter()
        if target[0] == "update":
            item = target[1]
            if isinstance(item, Schedule):
                patched = _apply_schedule_amendment(item.text or "", change.amendment_text)
                item.text = patched if patched is not None else _llm_apply(llm, item.text or "", change.amendment_text)
            else:
                item.text = _llm_apply(llm, item.text or "", change.amendment_text)
            label = getattr(item, "no", None) or getattr(item, "name", None) or "schedule"
            print(f"Updated: {label} ({time.perf_counter() - started:.1f}s)", flush=True)
        else:
            _, section, subregulation_no = target
            new_text = _llm_apply(llm, "", change.amendment_text)
            elapsed = time.perf_counter() - started
            if not new_text:
                print(f"Skipped insert (empty LLM output): {subregulation_no} ({elapsed:.1f}s)", flush=True)
                continue
            section.sub_sections.append(Subsection(no=subregulation_no, text=new_text))
            print(f"Inserted sub-regulation: {subregulation_no} ({elapsed:.1f}s)", flush=True)


def _build_llm(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        base_url=OPENROUTER_BASE_URL,
        api_key=os.environ["OPENROUTER_API_KEY"],
        temperature=LLM_TEMPERATURE,
    )


def apply_amendment_to_regulation(
    regulation: Regulation,
    amendment: AmendmentList,
    llm=None,
    model: str = DEFAULT_MODEL,
) -> Regulation:
    """Apply every change from an amendment onto an in-memory regulation."""
    llm = llm or _build_llm(model)

    groups: dict[int, list] = {}
    for change in amendment.changes:
        target = _find_target(regulation, change)
        if target is None:
            print(f"Skipped (no matching target): {change.model_dump()}", flush=True)
            continue
        groups.setdefault(id(target[1]), []).append((change, target))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(_process_group, llm, group) for group in groups.values()]
        for future in futures:
            future.result()
    return regulation


def _write_regulation(regulation: Regulation, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(regulation.model_dump(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def apply_amendment(
    regulation_json_path: str | Path,
    amendment_json_path: str | Path,
    output_json_path: str | Path | None = None,
    model: str = DEFAULT_MODEL,
) -> Regulation:
    """Apply every change from an amendment JSON onto a regulation JSON.

    Both files are read into pydantic objects. The updated regulation is written
    to ``regulation.final.json`` next to the input regulation unless
    ``output_json_path`` is given. The resulting ``Regulation`` is returned.
    """
    regulation = Regulation.model_validate_json(Path(regulation_json_path).read_text(encoding="utf-8"))
    amendment = AmendmentList.model_validate_json(Path(amendment_json_path).read_text(encoding="utf-8"))

    regulation = apply_amendment_to_regulation(regulation, amendment, model=model)

    output_path = (
        Path(output_json_path)
        if output_json_path
        else Path(regulation_json_path).parent / f"{Path(regulation_json_path).stem.rsplit('.', 1)[0]}.final.json"
    )
    _write_regulation(regulation, output_path)
    print(f"Final regulation written to: {output_path}")
    return regulation


def _amendment_date(path: Path) -> str:
    return AmendmentList.model_validate_json(path.read_text(encoding="utf-8")).date


def apply_amendments(
    regulation_json_path: str | Path,
    amendment_json_paths: Sequence[str | Path],
    output_json_path: str | Path | None = None,
    model: str = DEFAULT_MODEL,
) -> Regulation:
    """Apply a sequence of amendments onto a regulation, in date order.

    Amendments are applied cumulatively, earliest date first. When
    ``output_json_path`` is given the final regulation is written there; the
    resulting ``Regulation`` is always returned.
    """
    regulation = Regulation.model_validate_json(Path(regulation_json_path).read_text(encoding="utf-8"))
    ordered = sorted((Path(path) for path in amendment_json_paths), key=_amendment_date)
    llm = _build_llm(model)

    for amendment_path in ordered:
        amendment = AmendmentList.model_validate_json(amendment_path.read_text(encoding="utf-8"))
        started = time.perf_counter()
        print(f"Applying amendment {amendment.date}: {amendment_path}", flush=True)
        regulation = apply_amendment_to_regulation(regulation, amendment, llm=llm)
        print(f"Amendment {amendment.date} applied in {time.perf_counter() - started:.1f}s", flush=True)

    if output_json_path:
        _write_regulation(regulation, Path(output_json_path))
        print(f"Final regulation written to: {output_json_path}")
    return regulation
