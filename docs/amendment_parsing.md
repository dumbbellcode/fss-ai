# Amendment parsing — learnings & playbook

Compact notes on how FSSAI amendments are cleaned and parsed, the failure modes
found while processing regulation 02, and the rules now baked into the code.
Read this before touching `pre_processing/amendment_parser.py`,
`pre_processing/cleanup_markdown.py`, or `prompts/parse_amendment_prompt.py`.

## Pipeline (per regulation under `assets/regulations/<NN_Name>/`)

```
original/*.pdf  -convert->  converted/*.md  -clean->  cleaned/*.md  -parse->  parsed/*.json
              (amendments/)           (amendments/)          (amendments/)
```

Each stage's progress is recorded in `<regulation>/manifest.json`, keyed by a
hash of the **input** file. Re-running skips up-to-date files. After changing
cleanup or parsing code, the source hash is unchanged, so you must force a
regeneration (delete the `cleaned/`+`parsed/` entries for the files, or run with
`--force`).

## Convert stage — scanned PDFs (no text layer)

`utils/pdf_to_md.py` disables OCR by default because most FSSAI PDFs have a text
layer and OCR only adds noise. A handful of notifications are **pure scans**
(image-only, zero extractable text); with OCR off they convert to nothing and the
whole downstream chain is empty (the PDF is still "processed" — the failure is
silent).

`_pdf_has_text_layer` (via pymupdf) counts the text-layer characters; below 100
chars the file is treated as a scan and docling runs with
`TesseractCliOcrOptions(lang=["eng"], force_full_page_ocr=True)` (needs the
`tesseract` binary on `PATH`; falls back to no-OCR with a warning if unavailable).

Scans are OCR'd with Tesseract. Most are **English-only** (`eng`); the bilingual
Hindi-first gazettes need `eng,hin` so the Hindi comes out as real Devanagari and
`_cut_leading_hindi` can strip it. With `eng` alone that Hindi becomes *Latin*
gibberish that no Devanagari check can see, so it survives into `cleaned/`.

Language is controlled by `FSSAI_OCR_LANGS` (default `eng`); uninstalled codes are
dropped with a warning, and if nothing is installed OCR is skipped. The `hin`
model is not part of a plain tesseract install:

```bash
brew install tesseract-lang                       # or drop hin.traineddata in tessdata
FSSAI_OCR_LANGS=eng,hin .venv/bin/python utils/pdf_to_md.py <scan.pdf>
```

Do **not** make `eng,hin` the default: on English-only scans tesseract then reads
Latin text as Devanagari and mangles the header (verified on 02/amendments/84).

Scans that needed `eng,hin` (bilingual): `04/amendments/17_Notification_Antibiotics_Honey`,
`23/Regulation`, `24/Regulation`, `25/Regulation`. Verified image-only
notifications in this corpus:

```
02/amendments/80,81,82,84,85   03/amendments/17   04/amendments/17
05/amendments/03               16/amendments/05
23/Regulation  24/Regulation  24/amendments/01   25/Regulation
```

`11/amendments/06_269202.pdf` looks empty (~576 cleaned chars) but *does* have a
text layer; it is simply a one-page document, not a scan.

Data-quality trap: `02/Compendium.pdf` is not a compendium at all — it is a
printout of the FSSAI website/chatbot page (nav links, `chatbotliveffrc` logo
paths, "Last Updated"). No cleaner can fix that; the source needs replacing.

## Clean stage — bilingual gazette layout

Almost every amendment PDF is **Hindi first, English second**, both as contiguous
blocks, but docling wrecks the seam:

- The English authority line is often merged into a Hindi line, e.g.
  `फा. सं. … MINISTRY OF HEALTH AND FAMILY WELFARE (FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA) NOTIFICATION New Delhi, the 29th January, 2019.`
- `New Delhi, the <date>` can sit several Hindi lines below a lone `## NOTIFICATION`.
- A few stray Hindi fragments survive at/after the seam.

`_notification_header_index` matches only *clean* standalone header shapes, so it
returned `None` on ~25 of 83 files in reg-02 and the Hindi was never cut. Fixes:

1. `_english_notification_index` fallback (used only when the strict detector
   fails). Anchors on English-only strings — `New Delhi, the <year>`,
   `FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA`, `NOTIFICATION`, `F. No.` — then
   walks back over adjacent English/blank lines to keep the preamble, stopping at
   any Devanagari line so it cannot re-enter the Hindi block.
2. `_drop_devanagari_lines` removes lines whose letters are **mostly Devanagari**
   (`deva > latin`). Mixed lines carrying the English header/citation are kept.
   It refuses to empty the document (returns the input if nothing would remain).

Result on reg-02: Hindi-dominant lines went from 2124→8 (file 48), 628→1 (29),
etc.; only 8/160 files keep any Devanagari, and those are single mixed header
lines (intentional).

### The main `Regulation.md` / `Compendium.md` are bilingual too

`cleanup_regulation` originally only removed the two gazette header strings, so
every bilingual regulation file kept its **entire leading Hindi block** — 15–33%
of the file was Devanagari (07: 15059 chars, 08: 36804, 20: 38633, 27: 58989).
The Hindi is sometimes real Devanagari and sometimes a **legacy-font
transliteration** (`vlk/kj.k`, `Hkkx III[k.M 4`, `ubZ fnYyh]`) that no Devanagari
check can see.

`cleanup_regulation` now runs the same two steps as the amendment cleaner:
`_cut_leading_hindi` cuts everything before the first English
notification/regulation start (`MINISTRY OF HEALTH AND FAMILY WELFARE`,
`FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA`, `F. No.`, `hereby makes the
following`, `Whereas the draft`), then `_drop_devanagari_lines` removes stray
Devanagari lines. The cut is **skipped when no Devanagari appears before the
English start**, so an already-English compendium (02's 1.29 M-char file) is
byte-identical. Verified deva→0 for 06–10, 20, 27 while 02 changed only by the
gazette-header removal.

Watch-outs found while auditing:

- The gazette order is Hindi-first, English-second, so a plain cut works; but the
  odd file interleaves (10 keeps a Devanagari line *after* the English start) —
  hence the follow-up `_drop_devanagari_lines` sweep is required, not optional.
- `_drop_devanagari_lines` treats a line as Hindi only when Devanagari letters
  outnumber Latin ones. Legacy-font Hindi is pure ASCII, so it is only removed by
  the leading-block cut, never by the sweep.

## Parse stage — chunking (`_split_amendment_document`)

Documents are split at *amendment-block boundaries* so one amendment's text never
spans two chunks; the notification prefix is repeated in each chunk. Markers in
`_SEMANTIC_MARKERS`:

- `_TOP_LEVEL_MARKER_RE` — clause headers `1. Short title…`, `2. In the Food
  Safety…`.
- `_CHANGE_ITEM_MARKER_RE` — change items `(1) in regulation …`, `- (a) in …`,
  `- (A) in Chapter …`, `(B) after APPENDIX …` (case-insensitive, `in|after`).
- `_SUBREGULATION_MARKER_RE` — structural headings `## '3.2.9 Preservatives`,
  `## 3.2.10 Acidity regulator`, `## 1. Sodium alginate:`.

`_marker_spans` de-duplicates matches by start offset because the patterns
overlap.

### Failure modes (all observed in reg-02)

1. **False boundary inside a subregulation.** The old top-level pattern included
   `\d+\.\s+\([A-Z]\)\s+(?:for|in)` compiled with `re.IGNORECASE`. It matched
   in-list items like `2. (a) in raw form` / `4. (c) in un-ground form`, splitting
   one subregulation across 3 chunks → duplicated fragments plus lost content
   (`44_Vertical_Standards`: sub-regulation 3.2.8's inserted block, 3.2.9, 3.2.10,
   parts of 3.2.11/3.2.12/3.2.14 vanished). 44 of 104 files were affected.
   *Fixed by removing that alternative and adding subregulation headings as
   boundaries.*
2. **Whole-section insertion not recognised.** Some notifications replace/insert a
   whole section using lettered sub-items under a bare stem clause
   (`2. In the … regulations, 2011,-` then `- (A) in Chapter 3 … 3.4 PROCESSING
   AIDS`, `(B) after APPENDIX B … APPENDIX C`). Neither the splitter nor the prompt
   treated `(A)`/`(B)` as changes, and the prompt had no rule for whole-section
   insertions, so the model returned `changes: []`
   (`15_Processing_Aids`: 44-byte JSON). *Fixed by the marker change + prompt rules
   6–7.*
3. **Output-cap loss for oversized blocks.** A block between `chunk_tokens`
   (8000) and `hard_chunk_tokens` (24000) is kept whole; the model then can't
   reproduce its verbatim `amendment_text` within `max_tokens` (16384) and silently
   drops/truncates entries (no code path deletes changes). Mitigations: finer
   boundaries (fix 1) so blocks stay small, plus prompt rule 7 (keep the lead-in
   and heading, omit an oversized table body).
4. **Structured-output loops.** `with_structured_output(AmendmentList)` (tool
   calling) intermittently runs to the completion cap (`LengthFinishReasonError`)
   while the *same* prompt returns clean short JSON in plain mode. Raising
   `max_tokens` only loops longer. They are handled by:
   - `LengthFinishReasonError` is **not** retried (it is not transient);
   - `_invoke_amendment` falls back to `_invoke_plain_json`, which asks for JSON
     only, strips code fences, validates with pydantic, and retries on validation
     errors.
5. **Provider pinning causes silent empty results.** With
   `provider_order=("coreweave",)` gpt-oss-120b intermittently answers
   `finish_reason=stop` with **no tool call**; `with_structured_output` turns that
   into an empty `changes` list and no error, so a chunk yields nothing
   (44_Vertical_Standards returned 2 changes instead of 20+). A raw probe showed
   `tool_calls=0` on coreweave vs `tool_calls=1`/11 changes on OpenRouter default
   routing. `provider_order` now defaults to empty (let OpenRouter choose) and
   `extra_body` is sent only when a pin is configured — in both `amendment_parser`
   and `apply_amendment`.
6. **Lazy / elided output (the main remaining failure mode).** The model
   sometimes refuses to copy long bodies and emits an ellipsis instead:
   - a tiny placeholder such as `in ... ...`;
   - a synthesised sentence such as
     `Now, therefore, ... makes the following regulations further to amend the ... Regulations`;
   - a truncated instruction such as `In Table 1, after ... (text truncated)`.
   `_has_elision` flags a *short, single-line* text containing `...`/`…`
   (verbatim bodies are long and multi-line), and `_result_is_degenerate` routes
   any chunk with such a change to the plain-JSON fallback. Prompt rules 8–9 also
   forbid ellipses and forbid turning the preamble / closing citation list into
   changes.
7. **Model fidelity ceiling (unresolved).** gpt-oss-120b is *flaky* at
   verbatim-echoing large bodies: the same chunk can return the full block one run
   and a preamble-duplicated stub the next. Consequences: a change's
   `amendment_text` may be an empty-ish stub, and a document can yield junk
   entries whose target is the preamble. Smaller `amendment_parser_chunk_tokens`
   reduces the copy demand; the general fix would be to take the inserted body
   from the source markdown instead of asking the model to copy it.

### Prompt rules that matter (`prompts/parse_amendment_prompt.py`)

- Treat uppercase lettered sub-items `(A)`, `(B)` as changes even under a stem
  clause.
- Whole-section insert/substitution → one change; set `regulation` to the new
  section number (e.g. `3.4`) or `annexure`/`schedule` to the new
  appendix/schedule, else leave targets null; start `amendment_text` with the
  lead-in and include the new heading.
- Never emit an empty `changes` list when the document has an insert/substitute
  instruction; do not emit a change for `1. Short title and commencement`.
- Never abbreviate with `...`/`…`; end at a clean boundary instead (rule 8).
- Ignore the preamble and the closing "Note. - The principal regulations were
  published … (I) F. No. …" citation list; they are not amendments (rule 9).
- Schedule-first disambiguation, one target per change, all six fields present.

## Auditing a parse pass

`utils/audit_parsed_amendments.py` compares each `parsed/amendments/*.json` with
its cleaned source (no API calls) and flags **empty** (no changes but the source
has change instructions), **elided** (`...` stubs) and **boilerplate**
(preamble-as-change) files. Run it after a pass and re-parse the flagged files:

```bash
.venv/bin/python utils/audit_parsed_amendments.py --dirs 02_,03_ --verbose
.venv/bin/python utils/generate_sample.py --stages parse --force \
    --dirs 02_Food_Products_Standards_and_Food_Additives
```

## Known residuals / follow-ups

- **`parse_regulation` does not understand the documents' numbering.** It only
  matches `CHAPTER <digits>` plus `N.M` sections and `N.M.K` subsections, but the
  gazette regulations use `CHAPTER I` (Roman) and `1. Short title and
  commencement`, `2. Definitions`. Result: `parsed/Regulation.json` is empty
  (`{"title":…,"chapters":[],"schedules":[]}`) for 8 of the 9 regulation
  documents parsed so far; even 02 only yields chapter 2 / section 2.10 out of a
  1.29 M-char document. This is a parse-stage blocker, not a clean-stage one.
- `48_Milk_Products` keeps 8 Devanagari lines (interleaved bilingual tables);
  acceptable but not perfect. Per-section language detection would be the general
  fix.
- Mixed header lines keep their Hindi prefix (they carry the English header); a
  line-level "strip Hindi prefix" pass could tidy these.
- Blocks between 8000–24000 tokens with no internal markers are still sent whole;
  if output loss recurs, lower `amendment_parser_hard_chunk_tokens` or add
  table-heading markers (risk: splitting mid-table).

## Verifying a change

```bash
.venv/bin/python -m pytest tests/unit -q
# blast-radius check for cleanup (no API calls): compare converted/*.md -> cleaned
# and confirm no file loses >90% and Devanagari stops increasing.
```

Regression guards in `tests/unit/test_amendment_parser.py`
(`test_top_level_marker_ignores_lettered_sub_items`,
`test_split_keeps_one_subregulation_together_and_is_lossless`, …) and
`tests/unit/test_cleanup_markdown.py`
(`test_cleanup_cuts_hindi_block_before_english_date`, …).
