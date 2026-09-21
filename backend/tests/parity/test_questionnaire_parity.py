"""Questionnaire validator parity — the PYTHON side.

Consumes the shared corpus at testdata/questionnaire_parity.json together
with frontend/src/parity/questionnaire.parity.test.ts (vitest). Both
languages must agree on every case: the server is authoritative, the TS
mirror drives the builder's live checks.
"""

import json
import pathlib

import pytest
from pydantic import ValidationError

from app.services.questionnaires import parse_format

CORPUS_PATH = (
    pathlib.Path(__file__).parents[3] / "testdata" / "questionnaire_parity.json"
)
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def _tpl(ref_or_doc):
    """Resolve a template reference (or pass an inline doc through)."""
    if isinstance(ref_or_doc, str):
        return CORPUS["templates"][ref_or_doc]
    return ref_or_doc


# --- score evaluation (both sides must produce the same number/null) ---------------


@pytest.mark.parametrize(
    "case", CORPUS["formula_evaluation"], ids=lambda c: c["name"]
)
def test_formula_evaluation(case):
    tpl = _tpl(case["template"])
    fmt = parse_format({**tpl, "score_formula": case["formula"]})
    assert fmt.score_of(case["answers"]) == case["expected"]


# --- formula validation (valid/invalid outcome parity; messages may differ) --------


@pytest.mark.parametrize(
    "case", CORPUS["formula_validation"], ids=lambda c: c["name"]
)
def test_formula_validation(case):
    doc = {"version": 1, "questions": case["questions"], "score_formula": case["formula"]}
    if case["valid"]:
        parse_format(doc)  # must not raise
    else:
        with pytest.raises(ValidationError):
            parse_format(doc)


# --- answer validation (exact backend message strings — the UI maps them) ----------


@pytest.mark.parametrize(
    "case", CORPUS["answer_validation"], ids=lambda c: c["name"]
)
def test_answer_validation(case):
    fmt = parse_format(_tpl(case["template"]))
    assert fmt.validate_answers(case["answers"]) == case["errors"]


# --- format document validation (server-authoritative matrix) ----------------------


@pytest.mark.parametrize(
    "case", CORPUS["format_validation"], ids=lambda c: c["name"]
)
def test_format_validation(case):
    if case["valid"]:
        parse_format(case["format"])  # must not raise
    else:
        with pytest.raises(ValidationError):
            parse_format(case["format"])


def test_error_string_contract_complete():
    """The contract list covers every error message the corpus uses — the
    frontend translation table (faAnswerError) is tested against exactly this
    list on the vitest side."""
    used = {m for c in CORPUS["answer_validation"] for m in c["errors"].values()}
    assert used <= set(CORPUS["error_string_contract"])
