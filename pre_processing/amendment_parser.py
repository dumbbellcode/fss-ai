#!/usr/bin/env python3
"""Extract amendments from a regulation amendment Markdown file using LangChain."""

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from prompts.parse_amendment_prompt import PARSE_AMENDMENT
from pre_processing.config import (
    AMENDMENT_PARSER_MODEL,
    LLM_TEMPERATURE,
    OPENROUTER_BASE_URL,
)


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


DEFAULT_MODEL = AMENDMENT_PARSER_MODEL

load_dotenv()


def parse_amendment(
    md_path: str | Path,
    output_json_path: str | Path | None = None,
    model: str = DEFAULT_MODEL,
) -> list[AmendmentItem]:
    """Extract amendments from an amendment Markdown file.

    When ``output_json_path`` is not given, the JSON is written next to the
    input file with a ``.json`` suffix.
    """
    output_path = Path(output_json_path) if output_json_path else Path(md_path).with_suffix(".json")
    document = Path(md_path).read_text(encoding="utf-8")
    llm = ChatOpenAI(
        model=model,
        base_url=OPENROUTER_BASE_URL,
        api_key=os.environ["OPENROUTER_API_KEY"],
        temperature=LLM_TEMPERATURE,
    ).with_structured_output(AmendmentList)

    result = llm.invoke([SystemMessage(content=PARSE_AMENDMENT), HumanMessage(content=document)])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result.changes
