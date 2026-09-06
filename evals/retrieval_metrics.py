"""Deterministic metadata metrics for retrieved regulation sources."""

from collections.abc import Mapping, Sequence
from math import log2
from typing import Any

from evals.schemas import GoldenSource

_SOURCE_FIELDS = (
    "regulation",
    "chapter",
    "section",
    "subsection",
    "schedule",
    "annexure",
    "form",
)


def _matches(expected: GoldenSource, retrieved: Mapping[str, Any]) -> bool:
    """Match all populated fields in a golden source against chunk metadata."""
    for field in _SOURCE_FIELDS:
        expected_value = getattr(expected, field)
        if expected_value is None:
            continue
        retrieved_value = retrieved.get(field)
        if field == "chapter" and isinstance(retrieved_value, str):
            retrieved_value = retrieved_value.removeprefix("Chapter ")
            try:
                retrieved_value = int(retrieved_value)
            except ValueError:
                return False
        if retrieved_value != expected_value:
            return False
    return True


def calculate_metadata_metrics(
    expected_sources: Sequence[GoldenSource],
    retrieved_metadata: Sequence[Mapping[str, Any]],
    *,
    k: int,
) -> dict[str, float]:
    """Calculate source-metadata precision, recall, and nDCG at ``k``.

    Expected sources are partial locators: omitted fields are wildcards. Recall
    counts each expected source once, so multiple chunks from the same source do
    not inflate coverage. Precision counts relevant retrieved chunks, which
    reflects the amount of relevant context sent to the generator.
    """
    if not expected_sources:
        raise ValueError("expected_sources must not be empty")
    if k < 1:
        raise ValueError("k must be at least 1")

    top_chunks = list(retrieved_metadata[:k])
    matched_source_indexes: set[int] = set()
    relevant_chunks = 0
    gains: list[int] = []
    for metadata in top_chunks:
        matching_indexes = {
            index
            for index, expected in enumerate(expected_sources)
            if _matches(expected, metadata)
        }
        if matching_indexes:
            relevant_chunks += 1
        new_matches = matching_indexes - matched_source_indexes
        gains.append(1 if new_matches else 0)
        matched_source_indexes.update(matching_indexes)

    precision = relevant_chunks / len(top_chunks) if top_chunks else 0.0
    recall = len(matched_source_indexes) / len(expected_sources)
    dcg = sum(gain / log2(rank + 1) for rank, gain in enumerate(gains, start=1))
    ideal_gains = [1] * min(len(expected_sources), k)
    ideal_dcg = sum(
        gain / log2(rank + 1)
        for rank, gain in enumerate(ideal_gains[:k], start=1)
    )
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
    return {
        "precision_at_k": precision,
        "recall_at_k": recall,
        "ndcg_at_k": ndcg,
    }
