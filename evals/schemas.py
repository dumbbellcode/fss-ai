"""Pydantic schemas for retrieval evaluation goldens."""

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


class GoldenSource(BaseModel):
    """A source location expected to support a golden answer."""

    model_config = ConfigDict(extra="forbid")

    regulation: str = Field(min_length=1)
    chapter: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, min_length=1)
    subsection: str | None = Field(default=None, min_length=1)
    schedule: str | None = Field(default=None, min_length=1)
    annexure: str | None = Field(default=None, min_length=1)
    form: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def has_location(self) -> "GoldenSource":
        if not any(
            value is not None
            for value in (
                self.chapter,
                self.section,
                self.subsection,
                self.schedule,
                self.annexure,
                self.form,
            )
        ):
            raise ValueError("expected source must include a location besides regulation")
        return self


class Golden(BaseModel):
    """One question, reference answer, and expected source set."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    expected_sources: list[GoldenSource] = Field(min_length=1)


class GoldenDataset(RootModel[list[Golden]]):
    """The JSON array stored in an ``ai-generated.json`` golden file."""

    root: list[Golden] = Field(min_length=1)
