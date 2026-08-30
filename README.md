# FSSAI RAG

> **Status: WIP** — Work in progress. APIs, schema, and pipeline behavior may change without notice.

Tooling to download, convert, parse, and search Indian FSSAI food safety regulations and their amendments.

## Overview

The pipeline turns FSSAI regulation PDFs into structured JSON that can be fed into a RAG (retrieval-augmented generation) system:

1. **Download** — fetch regulation/amendment PDFs from FSSAI.
2. **Convert** — PDF → Markdown (`*.converted.md`).
3. **Clean** — strip gazette headers/footers (`*.cleaned.md`).
4. **Parse** — regulation Markdown → structured JSON (chapters/sections/sub-sections/schedules/forms) (`*.cleaned.json`).
5. **Amendments** — use an LLM to extract amendment changes (`date` + `changes`) from amendment notifications.
6. **Apply** — use an LLM to apply amendment changes onto the parsed regulation JSON, producing `regulation.final.json`.

## Project layout

```
assets/regulations/          # downloaded PDFs + generated markdown/json (gitignored)
download_regulations.py      # fetch regulation PDFs
pre_processing/
  cleanup_markdown.py        # PDF -> cleaned markdown
  regulation_parser.py       # regulation markdown -> structured JSON + pydantic DTOs
  amendment_parser.py        # amendment markdown -> amendment JSON (LLM)
  apply_amendment.py         # apply amendment JSON onto regulation JSON (LLM)
utils/
  pdf_to_md.py               # PDF -> markdown conversion
  cleanup.py                 # remove generated artifacts
  generate_sample.py         # run the full sample pipeline
prompts/                     # LLM prompt templates
tests/                       # pytest unit tests
```

## Requirements

- Python 3.12 (managed with `uv`)
- An OpenRouter API key in a `.env` file (`OPENROUTER_API_KEY=...`) for the LLM-based steps

## Quick start

```bash
uv sync
cp .env.example .env        # add your OPENROUTER_API_KEY
uv run pytest               # run unit tests
uv run python utils/generate_sample.py   # run pipeline on sample directories
```

## Notes

- Generated assets under `assets/` and the `.env` file are gitignored.
- The LLM steps use `openai/gpt-4o-mini` (apply) and `deepseek/deepseek-v4-flash` (extract) on OpenRouter by default.

## Roadmap

- [ ] Index parsed regulations for retrieval
- [ ] Add a query/answer interface
- [ ] Expand coverage to all FSSAI regulations