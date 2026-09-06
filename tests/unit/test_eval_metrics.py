from unittest.mock import Mock, patch

from evals.metrics import calculate_context_metrics


def test_calculate_context_metrics_builds_deepeval_case():
    precision = Mock(score=0.8, reason="precision reason")
    recall = Mock(score=0.9, reason="recall reason")
    precision_cls = Mock(return_value=precision)
    recall_cls = Mock(return_value=recall)

    with patch("evals.metrics.ContextualPrecisionMetric", precision_cls), patch(
        "evals.metrics.ContextualRecallMetric", recall_cls
    ):
        result = calculate_context_metrics(
            "What is required?",
            "A valid license is required.",
            ["Chapter 2\n\nA valid license is required."],
        )

    assert result == {
        "contextual_precision": 0.8,
        "contextual_precision_reason": "precision reason",
        "contextual_recall": 0.9,
        "contextual_recall_reason": "recall reason",
    }
    precision.measure.assert_called_once()
    recall.measure.assert_called_once()
    case = precision.measure.call_args.args[0]
    assert case.input == "What is required?"
    assert case.expected_output == "A valid license is required."
    assert case.retrieval_context == ["Chapter 2\n\nA valid license is required."]
