#!/usr/bin/env python3
"""Run the PDF-to-JSON preprocessing pipeline for sample regulations and amendments.

Supports full generation (all stages) or a subset of stages via ``--stages``.
Processing is incremental: a stage is skipped when its output already exists and
the source file is unchanged (tracked in ``<directory>/manifest.json``).
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pre_processing.amendment_parser import parse_amendment
from pre_processing.apply_amendment import apply_amendments
from pre_processing.cleanup_markdown import cleanup_amendment, cleanup_regulation
from pre_processing.pipeline import Item, Manifest, Stage, run_pipeline
from pre_processing.regulation_parser import parse_regulation
from pre_processing.config import DEFAULT_CONFIG, PreprocessingConfig
from ingestion.config import DEFAULT_CONFIG as DEFAULT_INGESTION_CONFIG, IngestionConfig
from ingestion.persist_embeddings import ingest_regulation
from utils.pdf_to_md import ConversionMethod, convert_pdf

SAMPLE_DIRECTORIES = [
    PROJECT_ROOT / "assets/regulations/02_Food_Products_Standards_and_Food_Additives",
]

ALL_STAGE_NAMES = ("convert", "clean", "parse", "post_amendment", "ingestion")


def build_stages(
    method: ConversionMethod,
    config: PreprocessingConfig = DEFAULT_CONFIG,
    ingestion_config: IngestionConfig = DEFAULT_INGESTION_CONFIG,
) -> list[Stage]:
    def convert(src: Path, dst: Path) -> None:
        convert_pdf(src, method, output_path=dst)

    def parse_regulation_stage(src: Path, dst: Path) -> None:
        result = parse_regulation(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")

    def post_amendment_stage(src: Path, dst: Path) -> None:
        amendments = sorted((src.parent / "amendments").glob("*.json"))
        apply_amendments(src, amendments, output_json_path=dst, config=config)

    def ingestion_stage(src: Path, dst: Path) -> None:
        chroma_dir = PROJECT_ROOT / ingestion_config.persist_dir
        count = ingest_regulation(
            src,
            collection_name=ingestion_config.collection_name,
            persist_dir=chroma_dir,
            config=ingestion_config,
        )
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(
            json.dumps(
                {
                    "collection": ingestion_config.collection_name,
                    "documents": count,
                    "embedding_model": ingestion_config.embedding_model,
                    "chunk_size_tokens": ingestion_config.chunk_size_tokens,
                    "chunk_overlap_tokens": ingestion_config.chunk_overlap_tokens,
                    "chroma_dir": str(chroma_dir),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    return [
        Stage("convert", "original", ".pdf", "converted", ".md", convert),
        Stage(
            "clean",
            "converted",
            ".md",
            "cleaned",
            ".md",
            {"regulation": cleanup_regulation, "amendment": cleanup_amendment},
        ),
        Stage(
            "parse",
            "cleaned",
            ".md",
            "parsed",
            ".json",
            {
                "regulation": parse_regulation_stage,
                "amendment": lambda src, dst: parse_amendment(src, dst, config=config),
            },
            only=lambda kind, stem: kind == "amendment" or stem == "Regulation",
        ),
        Stage(
            "post_amendment",
            "parsed",
            ".json",
            "post_amendment",
            ".final.json",
            {"regulation": post_amendment_stage},
            only=lambda kind, stem: kind == "regulation" and stem == "Regulation",
            dependencies=lambda item: [
                item.root / "parsed" / f"{item.base_stem}.json",
                *sorted((item.root / "parsed" / "amendments").glob("*.json")),
            ],
        ),
        Stage(
            "ingestion",
            "post_amendment",
            ".final.json",
            "ingestion",
            ".ingested.json",
            {"regulation": ingestion_stage},
            only=lambda kind, stem: kind == "regulation" and stem == "Regulation",
            dependencies=lambda item: [
                item.root / "post_amendment" / f"{item.base_stem}.final.json",
                *sorted((PROJECT_ROOT / "ingestion").glob("*.py")),
            ],
        ),
    ]


def discover_items(directory: Path) -> list[Item]:
    items = [
        Item(kind="regulation", base_stem=pdf.stem, root=directory)
        for pdf in sorted((directory / "original").glob("*.pdf"))
    ]
    items += [
        Item(kind="amendment", base_stem=pdf.stem, root=directory, sub="amendments")
        for pdf in sorted((directory / "original" / "amendments").glob("*.pdf"))
    ]
    return items


def parse_stages(value: str | None) -> list[str]:
    if not value:
        return list(ALL_STAGE_NAMES)
    names = [name.strip() for name in value.split(",") if name.strip()]
    unknown = set(names) - set(ALL_STAGE_NAMES)
    if unknown:
        raise ValueError(
            f"Unknown stage(s): {', '.join(sorted(unknown))}. Valid stages: {', '.join(ALL_STAGE_NAMES)}"
        )
    return names


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the PDF-to-JSON preprocessing pipeline for sample directories."
    )
    parser.add_argument(
        "--method",
        choices=("markitdown", "pymupdf"),
        default="markitdown",
        help="PDF conversion method (default: markitdown)",
    )
    parser.add_argument(
        "--stages",
        default=None,
        help=f"Comma-separated subset of stages to run ({', '.join(ALL_STAGE_NAMES)}). Default: all.",
    )
    parser.add_argument("--force", action="store_true", help="Re-run stages even when outputs are up to date.")
    args = parser.parse_args()

    selected = parse_stages(args.stages)
    stages = build_stages(args.method)

    for directory in SAMPLE_DIRECTORIES:
        manifest = Manifest(directory / "manifest.json")
        results = run_pipeline(discover_items(directory), stages, manifest, selected=selected, force=args.force)
        for result in results:
            verb = "Skipped (up to date)" if result.skipped else f"Ran {result.stage}"
            print(f"  {verb}: {result.path}")
        print(f"Manifest: {manifest.path}")


if __name__ == "__main__":
    main()
