"""DeepEval metrics used to evaluate retrieved regulation context."""

from collections.abc import Sequence
from typing import Any

from deepeval.metrics import ContextualPrecisionMetric, ContextualRecallMetric
from deepeval.test_case import LLMTestCase


def calculate_context_metrics(
    question: str,
    expected_answer: str,
    retrieval_context: Sequence[str],
    *,
    model: Any | None = None,
) -> dict[str, float | str | None]:
    """Calculate DeepEval contextual precision and recall for one query.

    ``expected_answer`` is used as the reference answer because contextual
    precision and recall judge whether the retrieved context supports the
    expected answer. This is a retrieval-only evaluation, so ``actual_output``
    is intentionally left unset.
    """
    if not question.strip():
        raise ValueError("question must not be empty")
    if not expected_answer.strip():
        raise ValueError("expected_answer must not be empty")
    if not retrieval_context:
        raise ValueError("retrieval_context must not be empty")

    test_case = LLMTestCase(
        input=question,
        expected_output=expected_answer,
        retrieval_context=list(retrieval_context),
    )
    metric_kwargs = {"model": model} if model is not None else {}
    precision = ContextualPrecisionMetric(include_reason=True, **metric_kwargs)
    recall = ContextualRecallMetric(include_reason=True, **metric_kwargs)
    precision.measure(test_case)
    recall.measure(test_case)

    return {
        "contextual_precision": precision.score,
        "contextual_precision_reason": precision.reason,
        "contextual_recall": recall.score,
        "contextual_recall_reason": recall.reason,
    }
