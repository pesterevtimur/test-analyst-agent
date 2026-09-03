"""The reference set as typed data.

Each question is one YAML file, and one file is one question, so the git history
shows when a question was written and against which state of the project. That
ordering is the whole mitigation for the set being written by the author of the
agent: questions and gold SQL land before the prompt exists (SPEC, section 8).

Two subsets with different rules:

    open/    twenty questions, used while building
    sealed/  ten questions, run once at the end

The gap between accuracy on the two is the measure of how much the agent was
fitted to the questions it could see.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Difficulty(StrEnum):
    """The three classes from SPEC, section 9. Used for both quality and money:
    hours saved are counted per class, so accuracy has to be reported per class."""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class Kind(StrEnum):
    ANSWERABLE = "answerable"
    # A question whose right answer is a refusal. Six of the thirty.
    TRAP = "trap"


class TrapType(StrEnum):
    PII = "pii"
    OUT_OF_SCOPE = "out-of-scope"
    AMBIGUOUS = "ambiguous"
    NO_DATA = "no-data"


class GuardExpectation(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    # For traps where no SQL should be written at all: there is nothing for the
    # guard rails to see, and that is the point.
    NOT_APPLICABLE = "not-applicable"


class Expectation(BaseModel):
    """How the answer is compared. Result first, SQL text never (ADR-001)."""

    model_config = ConfigDict(frozen=True)

    key_columns: list[str] = Field(default_factory=list)
    measure_columns: list[str] = Field(default_factory=list)
    # Relative tolerance on measures. 0.5% by default, per SPEC section 8.
    tolerance: float = 0.005
    guard: GuardExpectation = GuardExpectation.PASSED

    # Trap fields.
    refusal_reason: str = ""
    must_not: list[str] = Field(default_factory=list)
    should_offer: str = ""

    @model_validator(mode="after")
    def _upper(self) -> Expectation:
        # Oracle returns column names upper case; comparing them case-sensitively
        # would turn a formatting difference into a wrong answer.
        object.__setattr__(self, "key_columns", [c.upper() for c in self.key_columns])
        object.__setattr__(
            self, "measure_columns", [c.upper() for c in self.measure_columns]
        )
        return self


class Question(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    question: str
    asked_by: str = ""
    difficulty: Difficulty
    kind: Kind
    trap_type: TrapType | None = None
    metrics: list[str] = Field(default_factory=list)
    # Ids of the traps in the semantic layer this question walks into. Used to
    # check the set covers the documented traps rather than the easy paths.
    gotchas: list[str] = Field(default_factory=list)
    expected_tools: list[str] = Field(default_factory=list)
    max_steps: int = 10
    gold_sql: str | None = None
    expect: Expectation
    notes: str = ""

    @property
    def sealed(self) -> bool:
        return self.id.startswith("sealed-")

    @model_validator(mode="after")
    def _consistent(self) -> Question:
        if self.kind is Kind.ANSWERABLE:
            if not self.gold_sql or not self.gold_sql.strip():
                raise ValueError(f"{self.id}: answerable question without gold SQL")
            if not self.expect.measure_columns:
                raise ValueError(
                    f"{self.id}: answerable question without measure columns; "
                    "there would be nothing to compare"
                )
            if self.trap_type is not None:
                raise ValueError(f"{self.id}: answerable question with a trap type")
        else:
            if self.gold_sql:
                raise ValueError(
                    f"{self.id}: a trap has no gold SQL. The right answer is a "
                    "refusal, and writing SQL for it would make the refusal look "
                    "like a failure to answer."
                )
            if self.trap_type is None:
                raise ValueError(f"{self.id}: trap without a trap type")
            if not self.expect.refusal_reason.strip():
                raise ValueError(f"{self.id}: trap without a refusal reason")
            if not self.expect.must_not:
                raise ValueError(
                    f"{self.id}: trap without forbidden behaviour. A refusal that "
                    "cannot be graded is not a test."
                )
        return self


class Dataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    questions: list[Question]

    @property
    def open(self) -> list[Question]:
        return [q for q in self.questions if not q.sealed]

    @property
    def sealed(self) -> list[Question]:
        return [q for q in self.questions if q.sealed]

    @property
    def traps(self) -> list[Question]:
        return [q for q in self.questions if q.kind is Kind.TRAP]

    @property
    def answerable(self) -> list[Question]:
        return [q for q in self.questions if q.kind is Kind.ANSWERABLE]

    def by_id(self, question_id: str) -> Question:
        for question in self.questions:
            if question.id == question_id:
                return question
        raise KeyError(question_id)


def _read(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return data


def default_root() -> Path:
    return Path(__file__).resolve().parents[2] / "dataset"


def load_dataset(root: Path | None = None) -> Dataset:
    """Read every question under root, refusing anything inconsistent.

    Loading is strict on purpose: a reference set that silently drops a
    malformed question reports a better score than it earned.
    """
    root = root or default_root()
    questions: list[Question] = []
    seen: dict[str, Path] = {}

    for subset in ("open", "sealed"):
        directory = root / subset
        if not directory.is_dir():
            raise FileNotFoundError(f"{directory} does not exist")
        for path in sorted(directory.glob("*.yaml")):
            question = Question.model_validate(_read(path))
            if not question.id.startswith(f"{subset}-"):
                raise ValueError(
                    f"{path}: id {question.id!r} does not match its subset "
                    f"{subset!r}. The subset is what decides whether the question "
                    "may be used while building."
                )
            if question.id in seen:
                raise ValueError(
                    f"{path}: id {question.id!r} already used by {seen[question.id]}"
                )
            seen[question.id] = path
            questions.append(question)

    return Dataset(questions=questions)
