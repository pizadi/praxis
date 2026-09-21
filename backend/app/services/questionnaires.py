"""Questionnaire format + answer validation.

The format document is the single source of truth for what a template
accepts. It is validated with pydantic on every write path (API create/
update and JSON upload all funnel through here), so hand-written and
builder-produced JSON get identical treatment.

Answers are validated against a format at write time. Stored answers stay
raw (nullable keys); when the template is later edited the render side
merges and flags invalid values — see schemas/render helpers.
"""

import json
import re
import typing as t
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.scoring import (
    MAX_FORMULA_LENGTH,
    Formula,
    FormulaError,
    evaluate_formula,
    parse_formula,
    validate_refs,
)

KEY_RE = re.compile(r"^[a-z0-9_]{1,64}$")

QUESTION_TYPES = ("number", "choice", "string")


class NumberQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str = Field(min_length=1, max_length=256)
    type: t.Literal["number"]
    required: bool = False
    min: float | None = None
    max: float | None = None
    integer: bool = False
    unit: str = Field(default="", max_length=32)

    @field_validator("key")
    @classmethod
    def key_format(cls, v: str) -> str:
        if not KEY_RE.match(v):
            raise ValueError("question key must match [a-z0-9_] (max 64 chars)")
        return v

    @model_validator(mode="after")
    def range_ok(self) -> "NumberQuestion":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min must be <= max")
        return self


class ChoiceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=128)
    score: float | None = None


class ChoiceQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str = Field(min_length=1, max_length=256)
    type: t.Literal["choice"]
    required: bool = False
    options: list[ChoiceOption] = Field(min_length=2, max_length=50)

    @field_validator("key")
    @classmethod
    def key_format(cls, v: str) -> str:
        if not KEY_RE.match(v):
            raise ValueError("question key must match [a-z0-9_] (max 64 chars)")
        return v

    @field_validator("options")
    @classmethod
    def unique_values(cls, opts: list[ChoiceOption]) -> list[ChoiceOption]:
        values = [o.value for o in opts]
        if len(values) != len(set(values)):
            raise ValueError("option values must be unique within a question")
        return opts


class StringQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str = Field(min_length=1, max_length=256)
    type: t.Literal["string"]
    required: bool = False
    multiline: bool = False
    max_length: int = Field(default=10000, ge=1, le=10000)

    @field_validator("key")
    @classmethod
    def key_format(cls, v: str) -> str:
        if not KEY_RE.match(v):
            raise ValueError("question key must match [a-z0-9_] (max 64 chars)")
        return v


class QuestionnaireFormat(BaseModel):
    """Validated questionnaire format document (stored canonically as JSON)."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    title: str = Field(default="", max_length=256)
    questions: list[
        Annotated[NumberQuestion | ChoiceQuestion | StringQuestion, Field(discriminator="type")]
    ] = Field(min_length=1, max_length=200)
    # optional arithmetic formula over question keys for a total score
    # ("" = no scoring); validated below, evaluated by score_of().
    # Normalized (trimmed) so a whitespace-only value means "no scoring" —
    # matching the client-side mirror.
    score_formula: str = Field(default="", max_length=MAX_FORMULA_LENGTH)

    @field_validator("score_formula")
    @classmethod
    def strip_formula(cls, v: str) -> str:
        return v.strip()

    @field_validator("questions")
    @classmethod
    def unique_keys(cls, qs: list) -> list:
        keys = [q.key for q in qs]
        if len(keys) != len(set(keys)):
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            raise ValueError(f"duplicate question keys: {dupes}")
        return qs

    @model_validator(mode="after")
    def formula_ok(self) -> "QuestionnaireFormat":
        if self.score_formula:
            try:
                formula = parse_formula(self.score_formula)
                validate_refs(formula, {q.key: q.type for q in self.questions})
            except FormulaError as exc:
                raise ValueError(f"score formula: {exc}") from None
        return self

    # --- lookups ----------------------------------------------------------

    @property
    def keys(self) -> list[str]:
        return [q.key for q in self.questions]

    def question(self, key: str) -> NumberQuestion | ChoiceQuestion | StringQuestion | None:
        return next((q for q in self.questions if q.key == key), None)

    # --- score formula ------------------------------------------------------

    @property
    def has_scoring(self) -> bool:
        return bool(self.score_formula)

    def parsed_formula(self) -> Formula | None:
        """Parsed score formula (formats are validated, so this never raises)."""
        if not self.score_formula:
            return None
        return parse_formula(self.score_formula)

    def score_of(self, answers: dict) -> float | None:
        """Evaluate score_formula against raw answers.

        None when the template has no formula, or the formula cannot be
        computed (missing/invalid referenced answer, chosen option without a
        score, division by zero). Never raises on odd answer values.
        """
        formula = self.parsed_formula()
        if formula is None:
            return None
        return evaluate_formula(formula, lambda key: self._operand(key, answers))

    def _operand(self, key: str, answers: dict) -> float | None:
        """Numeric contribution of one question to the formula (None if N/A)."""
        q = self.question(key)
        if q is None:
            return None
        v = answers.get(key)
        if q.type == "number":
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return None
            return float(v)
        if q.type == "choice":
            if not isinstance(v, str):
                return None
            opt = next((o for o in q.options if o.value == v), None)
            if opt is None or opt.score is None:
                return None
            return float(opt.score)
        return None

    # --- answer validation --------------------------------------------------

    def validate_answers(self, answers: dict) -> dict[str, str]:
        """Return {key: error} for every invalid answer.

        Fields are nullable (explicitly): null/absent is ALWAYS valid, even
        for required questions — `required` is a form-level (UI) constraint.
        Unknown keys and type/range/choice violations are errors.
        """
        errors: dict[str, str] = {}
        valid_keys = set(self.keys)
        for k in answers:
            if k not in valid_keys:
                errors[k] = "unknown question key"
        for q in self.questions:
            v = answers.get(q.key)
            if v is None:
                continue
            if q.type == "number":
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    errors[q.key] = "must be a number"
                elif q.integer and not float(v).is_integer():
                    errors[q.key] = "must be an integer"
                elif (q.min is not None and v < q.min) or (q.max is not None and v > q.max):
                    errors[q.key] = f"must be between {q.min} and {q.max}"
            elif q.type == "choice":
                if not isinstance(v, str) or v not in {o.value for o in q.options}:
                    errors[q.key] = "must be one of the listed options"
            elif q.type == "string":
                if not isinstance(v, str):
                    errors[q.key] = "must be a string"
                elif len(v) > q.max_length:
                    errors[q.key] = f"max length {q.max_length}"
        return errors

    def dumps(self) -> str:
        """Canonical storage form (compact, order-preserving)."""
        return self.model_dump_json(exclude_none=False)


def parse_format(raw: str | bytes | dict) -> QuestionnaireFormat:
    """Parse + validate a format document from JSON text or a dict.

    Raises pydantic ValidationError (or json.JSONDecodeError) — callers
    translate that into a 422.
    """
    if isinstance(raw, (str, bytes)):
        raw = json.loads(raw)
    return QuestionnaireFormat.model_validate(raw)
