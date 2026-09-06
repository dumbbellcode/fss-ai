from math import log2

import pytest

from evals.retrieval_metrics import calculate_metadata_metrics
from evals.schemas import GoldenSource


def test_metadata_metrics_match_partial_sources_and_normalize_chapter():
    expected = [
        GoldenSource(
            regulation="R",
            chapter=2,
            section="2.1",
            subsection="2.1.1",
        ),
        GoldenSource(regulation="R", schedule="Schedule 2"),
    ]
    retrieved = [
        {"regulation": "R", "chapter": 1, "section": "1.1"},
        {
            "regulation": "R",
            "chapter": "Chapter 2",
            "section": "2.1",
            "subsection": "2.1.1",
        },
        {"regulation": "R", "schedule": "Schedule 2", "part": 3},
    ]

    result = calculate_metadata_metrics(expected, retrieved, k=3)

    assert result["precision_at_k"] == pytest.approx(2 / 3)
    assert result["recall_at_k"] == 1.0
    assert result["ndcg_at_k"] == pytest.approx(
        (1 / log2(3) + 1 / log2(4)) / (1 + 1 / log2(3))
    )


def test_metadata_metrics_do_not_count_duplicate_chunks_for_recall():
    expected = [GoldenSource(regulation="R", schedule="Schedule 2")]
    retrieved = [
        {"regulation": "R", "schedule": "Schedule 2", "part": 1},
        {"regulation": "R", "schedule": "Schedule 2", "part": 2},
    ]

    result = calculate_metadata_metrics(expected, retrieved, k=2)

    assert result["precision_at_k"] == 1.0
    assert result["recall_at_k"] == 1.0
