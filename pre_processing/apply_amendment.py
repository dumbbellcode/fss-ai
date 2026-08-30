#!/usr/bin/env python3
"""Apply amendments from an amendment JSON onto a parsed regulation JSON using LangChain."""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from pre_processing.amendment_parser import AmendmentItem, AmendmentList
from pre_processing.regulation_parser import Regulation, Subsection

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


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"
MAX_WORKERS = 5

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


def _llm_apply(llm, current_text: str, amendment_text: str, retries: int = 5) -> str:
    template = APPLY_AMENDMENT_PROMPT if current_text else INSERT_AMENDMENT_PROMPT
    prompt = template.format(current_text=current_text, amendment_text=amendment_text)
    text = ""
    for _ in range(retries):
        result = llm.invoke([SystemMessage(content=prompt)])
        text = result.content.strip()
        if len(text) >= 10 and not text.startswith("The current section text is not provided"):
            return text
    return text


def _process_group(llm, group: list) -> None:
    """Apply a group of changes targeting the same object, sequentially."""
    for change, target in group:
        if target[0] == "update":
            item = target[1]
            item.text = _llm_apply(llm, item.text or "", change.amendment_text)
            label = getattr(item, "no", None) or getattr(item, "name", None) or "schedule"
            print(f"Updated: {label}", flush=True)
        else:
            _, section, subregulation_no = target
            new_text = _llm_apply(llm, "", change.amendment_text)
            section.sub_sections.append(Subsection(no=subregulation_no, text=new_text))
            print(f"Inserted sub-regulation: {subregulation_no}", flush=True)


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

    llm = ChatOpenAI(
        model=model,
        base_url=OPENROUTER_BASE_URL,
        api_key=os.environ["OPENROUTER_API_KEY"],
        temperature=0,
    )

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

    output_path = (
        Path(output_json_path)
        if output_json_path
        else Path(regulation_json_path).parent / f"{Path(regulation_json_path).stem.rsplit('.', 1)[0]}.final.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(regulation.model_dump(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Final regulation written to: {output_path}")
    return regulation