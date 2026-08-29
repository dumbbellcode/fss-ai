#!/usr/bin/env python3
"""Parse extracted FSSAI regulation Markdown into structured JSON."""

import argparse
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Subsection(BaseModel):
    no: str
    text: str = ""


class Section(BaseModel):
    no: str
    text: str = ""
    sub_sections: list[Subsection] = Field(default_factory=list)


class Form(BaseModel):
    name: str
    text: str = ""


class Annexure(BaseModel):
    name: str
    text: str = ""


class Chapter(BaseModel):
    no: int
    title: str = ""
    sections: list[Section] = Field(default_factory=list)
    forms: list[Form] = Field(default_factory=list)


class Schedule(BaseModel):
    name: str
    forms: list[Form] = Field(default_factory=list)
    annexures: list[Annexure] = Field(default_factory=list)


class Regulation(BaseModel):
    chapters: list[Chapter] = Field(default_factory=list)
    schedules: list[Schedule] = Field(default_factory=list)


ItemType = Literal["chapter", "section", "subsection", "schedule", "annexure", "form"]

CHAPTER_RE = re.compile(r"^CHAPTER\s*-?\s*(\d+)\s*$", re.IGNORECASE)
SUBSECTION_RE = re.compile(r"^(\d+)\s*\.\s*(\d+)\s*\.\s*(\d+)\b")
SECTION_RE = re.compile(r"^(\d+)\s*\.\s*(\d+)\s*(?::|\s|$)")
SCHEDULE_RE = re.compile(r"^SCHEDULE\s*-?\s*([0-9]+|[IVXLCDM]+)\s*$", re.IGNORECASE)
ANNEXURE_RE = re.compile(r"^ANNEXURE\s*-?\s*(.+?)\s*$", re.IGNORECASE)
FORM_RE = re.compile(r"^['\"]?FORM(?:\s*-?\s*|\s+)(.+?)['\"]?\s*$", re.IGNORECASE)


def detect_item(line: str) -> tuple[ItemType, str] | None:
    """Return the document item represented by a line, if any."""
    value = line.strip()
    if match := CHAPTER_RE.fullmatch(value):
        return "chapter", match.group(1)
    if match := SCHEDULE_RE.fullmatch(value):
        return "schedule", match.group(1)
    if match := ANNEXURE_RE.fullmatch(value):
        return "annexure", match.group(1).strip(" '\"")
    if match := FORM_RE.fullmatch(value):
        return "form", match.group(1).strip(" '\"")
    if match := SUBSECTION_RE.match(value):
        return "subsection", ".".join(match.groups())
    if match := SECTION_RE.match(value):
        return "section", f"{match.group(1)}.{match.group(2)}"
    return None


def _text(lines: list[str]) -> str:
    return "\n".join(line.rstrip() for line in lines).strip()


def parse_regulation(md_path: str | Path) -> Regulation:
    """Parse a Markdown regulation into its structured representation."""
    lines = Path(md_path).read_text(encoding="utf-8").splitlines()
    regulation = Regulation()
    chapter: Chapter | None = None
    section: Section | None = None
    schedule: Schedule | None = None
    current: tuple[ItemType, object] | None = None

    def append_text(item: object, content: list[str]) -> None:
        value = _text(content)
        if not value:
            return
        if isinstance(item, Chapter):
            item.title = f"{item.title}\n{value}".strip()
        elif isinstance(item, (Section, Subsection, Form, Annexure)):
            item.text = f"{item.text}\n{value}".strip()

    def finish_item() -> None:
        nonlocal current
        if current is not None:
            append_text(current[1], content)
        current = None

    content: list[str] = []
    for line in lines:
        detected = detect_item(line)
        if detected:
            finish_item()
            item_type, number = detected
            content = []

            if item_type == "chapter":
                chapter = Chapter(no=int(number))
                regulation.chapters.append(chapter)
                section = None
                schedule = None
                current = (item_type, chapter)
            elif item_type == "section":
                section = Section(no=number)
                if chapter is not None and schedule is None:
                    chapter.sections.append(section)
                    current = (item_type, section)
                else:
                    current = None
            elif item_type == "subsection":
                subsection = Subsection(no=number)
                if section is not None and chapter is not None and schedule is None:
                    section.sub_sections.append(subsection)
                    current = (item_type, subsection)
                else:
                    current = None
            elif item_type == "schedule":
                schedule = Schedule(name=f"Schedule {number}")
                regulation.schedules.append(schedule)
                chapter = None
                section = None
                current = (item_type, schedule)
            elif item_type == "annexure":
                annexure = Annexure(name=f"Annexure-{number}")
                if schedule is not None:
                    schedule.annexures.append(annexure)
                    current = (item_type, annexure)
                else:
                    current = None
            elif item_type == "form":
                form = Form(name=f"Form {number}")
                if schedule is not None:
                    schedule.forms.append(form)
                    current = (item_type, form)
                elif chapter is not None:
                    chapter.forms.append(form)
                    current = (item_type, form)
                else:
                    current = None
        elif current is not None:
            content.append(line)

    finish_item()
    return regulation


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a regulation Markdown file into JSON.")
    parser.add_argument("md_path", type=Path)
    parser.add_argument("output_json_path", type=Path)
    args = parser.parse_args()

    result = parse_regulation(args.md_path)
    args.output_json_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_json_path.write_text(
        json.dumps(result.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Parsed JSON written to: {args.output_json_path}")


if __name__ == "__main__":
    main()
