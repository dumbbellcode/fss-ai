# FSSAI RAG

> **Status: WIP** — Work in progress. APIs, schema, and pipeline behavior may change without notice.

Tooling to download, convert, parse, and search Indian FSSAI food safety regulations and their amendments.

## Overview

The pipeline turns FSSAI regulation PDFs into structured JSON that can be fed into a RAG (retrieval-augmented generation) system:

1. **Download** — fetch regulation/amendment PDFs from FSSAI.
2. **Convert** — PDF → Markdown (`*.converted.md`).
3. **Clean** — strip gazette headers/footers (`*.cleaned.md`).
4. **Parse** — regulation Markdown → structured JSON (chapters/sections/sub-sections/schedules/forms) under `parsed/`.
5. **Amendments** — use an LLM to extract amendment changes (`date` + `changes`) from amendment notifications.
6. **Apply** — use an LLM to apply amendment changes onto the parsed regulation JSON, producing `regulation.final.json`.
7. **Ingest** — chunk the final regulation JSON, embed the chunks, and persist them to a Chroma vector store.

## Project layout

```
assets/regulations/          # downloaded PDFs + generated markdown/json (gitignored)
download_regulations.py      # fetch regulation PDFs
pre_processing/
  config.py                # preprocessing model and LLM settings
  cleanup_markdown.py        # PDF -> cleaned markdown
  regulation_parser.py       # regulation markdown -> structured JSON + pydantic DTOs
  amendment_parser.py        # amendment markdown -> amendment JSON (LLM)
  apply_amendment.py         # apply amendment JSON onto regulation JSON (LLM)
ingestion/
  config.py                # injectable chunking / embedding / chroma settings
  chunks_creator.py        # regulation JSON -> text chunks with metadata
  create_embeddings.py     # chunks -> embeddings (OpenRouter)
  persist_embeddings.py    # chunks + embeddings -> Chroma
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
uv run pytest               # run unit tests (excludes integration)
uv run python utils/generate_sample.py                    # run all stages
uv run python utils/generate_sample.py --stages clean,parse   # run a subset
uv run python utils/generate_sample.py --force            # ignore incremental cache
```

The pipeline is incremental: each stage is skipped when its output already exists
and the source is unchanged, tracked in `<directory>/manifest.json`. Stages are
`convert` (PDF → `.converted.md`), `clean` (`.converted.md` → `.cleaned.md`),
`parse` (`cleaned/<stem>.md` → `parsed/<stem>.json`), `post_amendment` (`parsed/*.json`
→ `post_amendment/*.final.json`), and `ingestion` (final JSON → Chroma).

### Ingestion

```bash
# chunk the final regulation JSON and write embeddings to a Chroma store
uv run python -m ingestion.persist_embeddings \
    assets/regulations/01_Licensing_and_Registration_of_Food_Businesses/post_amendment/Regulation.final.json

# or run the steps individually
uv run python -m ingestion.chunks_creator <regulation.json> chunks.json
uv run python -m ingestion.create_embeddings chunks.json embeddings.json
```

Each chapter section/subsection becomes a chunk of the form `Chapter: <title>\nSection:
<section>\n\n<subsection>`. Subsections (and schedule/annexure/form bodies) longer
than the chunk size are split with a LangChain `RecursiveCharacterTextSplitter` sized
by tokens (`cl100k_base`). Every chunk carries metadata: `regulation` (the
`Regulation.title` value), `chapter`, `section`, `subsection`, plus `part` when a subsection was
split. Embeddings default to `openai/text-embedding-3-large` on OpenRouter; the Chroma
collection defaults to `fssai_regulations` under `db/`. All values live in
`ingestion/config.py`.

### Benchmarking retrieval accuracy

Chunking and embedding are parameterized, so you can ingest the same regulation into
separate Chroma collections per configuration and compare accuracy:

```python
from ingestion.persist_embeddings import ingest_regulation

regulation = "assets/regulations/01_Licensing_and_Registration_of_Food_Businesses/post_amendment/Regulation.final.json"
for model in ["openai/text-embedding-3-small", "openai/text-embedding-3-large"]:
    for chunk_size in [200, 500, 1000]:
        ingest_regulation(
            regulation,
            collection_name=f"fssai_{model.split('/')[-1]}_{chunk_size}",
            model=model,
            chunk_size_tokens=chunk_size,
        )
```

The CLI exposes the same knobs via `--model`, `--chunk-size`, `--chunk-overlap`.

### Basic retrieval

Retrieve the most similar chunks for one question from the persisted collection:

```bash
uv run python -m retrieval.retrieve \
  "What are the requirements for registering a petty food business?" \
  --persist-dir db \
  --top-k 5
```

The Python API returns `RetrievedChunk` objects containing `text`, `metadata`,
and Chroma's `distance` score. Lower distance means greater similarity.

Integration tests that call the real LLM (accuracy checks) run with:

```bash
uv run pytest -m integration -s
```

## Notes

- Generated assets under `assets/`, the `.env` file, and the Chroma store under `db/` are gitignored.
- The LLM steps use `openai/gpt-4o-mini` (apply) and `google/gemini-2.5-flash-lite` (extract) on OpenRouter by default. Pass a `PreprocessingConfig` to the preprocessing functions to override models or runtime settings; keep `OPENROUTER_API_KEY` in the environment.

## Roadmap

- [x] Index parsed regulations for retrieval
- [ ] Add a query/answer interface
- [ ] Expand coverage to all FSSAI regulations
