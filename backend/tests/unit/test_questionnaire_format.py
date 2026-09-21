"""Questionnaire format-document validation matrix (unit level).

Server-authoritative: the pydantic QuestionnaireFormat is the single
validator every write path funnels through. The TS side deliberately has no
full mirror — its parity is tested via the API conformance cases in the
corpus (format_validation section) and the builder E2E specs.
"""

import pytest
from pydantic import ValidationError

from app.services.questionnaires import parse_format

Q_NUMBER = {"key": "a", "label": "A", "type": "number"}
Q_STRING = {"key": "s", "label": "S", "type": "string"}


def _doc(questions, **extra):
    return {"version": 1, "title": "t", "questions": questions, **extra}


def test_valid_minimal():
    f = parse_format(_doc([Q_NUMBER]))
    assert f.keys == ["a"]
    assert not f.has_scoring
    assert f.score_of({"a": 5}) is None


def test_valid_discriminated_union():
    f = parse_format(
        _doc(
            [
                {"key": "n", "label": "N", "type": "number",
                 "min": -1.5, "max": 2, "integer": False, "unit": "kg"},
                {"key": "c", "label": "C", "type": "choice",
                 "options": [{"value": "x", "label": "X", "score": 1.5},
                             {"value": "y", "label": "Y"}]},
                {"key": "s", "label": "S", "type": "string", "multiline": True, "max_length": 100},
            ]
        )
    )
    assert f.question("n").unit == "kg"
    assert f.question("c").options[1].score is None


def test_extra_forbid_everywhere():
    with pytest.raises(ValidationError):
        parse_format(_doc([Q_NUMBER], huh=1))
    with pytest.raises(ValidationError):
        parse_format(_doc([{**Q_NUMBER, "bogus": 1}]))
    with pytest.raises(ValidationError):
        # a NUMBER question carrying CHOICE-only fields
        parse_format(_doc([{**Q_NUMBER, "options": []}]))


def test_key_rules():
    with pytest.raises(ValidationError):
        parse_format(_doc([{"key": "Has Space", "label": "x", "type": "string"}]))
    with pytest.raises(ValidationError):
        parse_format(_doc([{"key": "", "label": "x", "type": "string"}]))
    parse_format(_doc([{"key": "a" * 64, "label": "x", "type": "string"}]))
    with pytest.raises(ValidationError):
        parse_format(_doc([{"key": "a" * 65, "label": "x", "type": "string"}]))
    with pytest.raises(ValidationError):
        parse_format(_doc([{"key": "کی", "label": "x", "type": "string"}]))  # non-ascii


def test_label_rules():
    with pytest.raises(ValidationError):
        parse_format(_doc([{"key": "a", "label": "", "type": "number"}]))


def test_unique_keys_message_names_the_dupes():
    with pytest.raises(ValidationError) as exc:
        parse_format(_doc([Q_STRING, {"key": "s", "label": "S2", "type": "string"}]))
    assert "s" in str(exc.value)


def test_number_range_check():
    parse_format(_doc([{"key": "n", "label": "x", "type": "number", "min": 0, "max": 0}]))
    with pytest.raises(ValidationError, match="min must be <= max"):
        parse_format(_doc([{"key": "n", "label": "x", "type": "number", "min": 10, "max": 0}]))


def test_choice_rules():
    # 2..50 options required, unique values
    with pytest.raises(ValidationError):
        parse_format(_doc([{"key": "c", "label": "x", "type": "choice", "options": []}]))
    with pytest.raises(ValidationError):
        parse_format(_doc([{"key": "c", "label": "x", "type": "choice",
                            "options": [{"value": "a", "label": "A"}]}]))
    dupopts = [{"value": "a", "label": "A"}, {"value": "a", "label": "A2"}]
    with pytest.raises(ValidationError):
        parse_format(_doc([{"key": "c", "label": "x", "type": "choice", "options": dupopts}]))
    opts = [{"value": f"v{i}", "label": f"L{i}"} for i in range(50)]
    parse_format(_doc([{"key": "c", "label": "x", "type": "choice", "options": opts}]))
    with pytest.raises(ValidationError):
        parse_format(_doc([{"key": "c", "label": "x", "type": "choice",
                            "options": opts + [{"value": "v51", "label": "L51"}]}]))


def test_string_max_length_bounds():
    parse_format(_doc([{"key": "s", "label": "x", "type": "string", "max_length": 1}]))
    with pytest.raises(ValidationError):
        parse_format(_doc([{"key": "s", "label": "x", "type": "string", "max_length": 0}]))
    with pytest.raises(ValidationError):
        parse_format(_doc([{"key": "s", "label": "x", "type": "string", "max_length": 10001}]))


def test_question_count_bounds():
    with pytest.raises(ValidationError):
        parse_format({"version": 1, "questions": []})
    # 200 max
    many = [{"key": f"q{i}", "label": "x", "type": "string"} for i in range(200)]
    parse_format(_doc(many))
    with pytest.raises(ValidationError):
        parse_format(_doc(many + [{"key": "q200", "label": "x", "type": "string"}]))


def test_score_formula_field_length_cap():
    # pydantic max_length fires before parsing
    with pytest.raises(ValidationError):
        parse_format(_doc([Q_NUMBER], score_formula="a+" * 600))


def test_dumps_round_trip():
    doc = _doc([Q_NUMBER], score_formula="a")
    f = parse_format(doc)
    assert parse_format(f.dumps()).keys == ["a"]
