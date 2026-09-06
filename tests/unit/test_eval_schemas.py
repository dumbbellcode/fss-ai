import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.evaluate_regulation import load_goldens
from evals.schemas import GoldenDataset


GOLDENS = (
    Path(__file__).resolve().parent.parent
    / "goldens"
    / "01_Licensing_and_Registration_of_Food_Businesses"
    / "ai-generated.json"
)


def test_golden_file_loads_as_pydantic_dtos():
    goldens = load_goldens(GOLDENS)

    assert len(goldens) == 10
    assert goldens[0].question
    assert goldens[0].expected_sources[0].regulation


def test_golden_dataset_rejects_unknown_fields():
    payload = [
        {
            "question": "Question",
            "answer": "Answer",
            "expected_sources": [{"regulation": "Regulation"}],
            "unexpected": True,
        }
    ]

    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(json.loads(json.dumps(payload)))
