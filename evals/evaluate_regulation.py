#!/usr/bin/env python3
"""Evaluate contextual precision and recall for a regulation golden set."""

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ingestion.config import DEFAULT_CONFIG as DEFAULT_INGESTION_CONFIG, IngestionConfig
from retrieval.retrieve import RetrievedChunk, retrieve

from evals.retrieval_metrics import calculate_metadata_metrics
from evals.schemas import Golden, GoldenDataset

DEFAULT_GOLDENS = Path(
    "tests/goldens/01_Licensing_and_Registration_of_Food_Businesses/ai-generated.json"
)


def load_goldens(path: str | Path) -> list[Golden]:
    """Load and validate the question/answer records in a golden file."""
    return GoldenDataset.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    ).root


def evaluate_goldens(
    goldens: Sequence[Golden],
    *,
    retrieve_fn: Callable[..., list[RetrievedChunk]] = retrieve,
    collection_name: str | None = None,
    persist_dir: str | Path | None = None,
    embedding_model: str | None = None,
    top_k: int = 5,
    ingestion_config: IngestionConfig = DEFAULT_INGESTION_CONFIG,
) -> dict[str, Any]:
    """Retrieve context and calculate metadata metrics for every golden."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    results: list[dict[str, Any]] = []
    collection_name = collection_name or ingestion_config.collection_name
    persist_dir = persist_dir or ingestion_config.persist_dir
    embedding_model = embedding_model or ingestion_config.embedding_model
    for index, golden in enumerate(goldens, start=1):
        chunks = retrieve_fn(
            golden.question,
            collection_name=collection_name,
            persist_dir=persist_dir,
            model=embedding_model,
            top_k=top_k,
            config=ingestion_config,
        )
        metadata_scores = calculate_metadata_metrics(
            golden.expected_sources,
            [chunk.metadata for chunk in chunks],
            k=top_k,
        )
        results.append(
            {
                "index": index,
                "question": golden.question,
                "expected_sources": [source.model_dump() for source in golden.expected_sources],
                "retrieved_sources": [chunk.metadata for chunk in chunks],
                "metadata_precision_at_k": metadata_scores["precision_at_k"],
                "metadata_recall_at_k": metadata_scores["recall_at_k"],
                "metadata_ndcg_at_k": metadata_scores["ndcg_at_k"],
            }
        )
    return {
        "count": len(results),
        "top_k": top_k,
        "summary": {
            "mean_metadata_precision_at_k": sum(
                result["metadata_precision_at_k"] for result in results
            ) / len(results),
            "mean_metadata_recall_at_k": sum(
                result["metadata_recall_at_k"] for result in results
            ) / len(results),
            "mean_metadata_ndcg_at_k": sum(
                result["metadata_ndcg_at_k"] for result in results
            ) / len(results),
        },
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate metadata precision, recall, and nDCG for regulation goldens."
    )
    parser.add_argument("--goldens", type=Path, default=DEFAULT_GOLDENS)
    parser.add_argument("--collection", default=DEFAULT_INGESTION_CONFIG.collection_name)
    parser.add_argument("--persist-dir", type=Path, default=DEFAULT_INGESTION_CONFIG.persist_dir)
    parser.add_argument("--embedding-model", default=DEFAULT_INGESTION_CONFIG.embedding_model)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path")
    args = parser.parse_args()

    report = evaluate_goldens(
        load_goldens(args.goldens),
        collection_name=args.collection,
        persist_dir=args.persist_dir,
        embedding_model=args.embedding_model,
        top_k=args.top_k,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
