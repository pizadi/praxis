"""Score-formula parser + evaluator unit tests.

Mirrors frontend/src/lib/questionnaire.ts (the TS side is tested against the
SAME cases in tests/parity via the shared corpus; these tests probe the
python implementation directly, including internals the corpus can't reach).
"""

import pytest

from app.services.scoring import (
    MAX_DEPTH,
    MAX_FORMULA_LENGTH,
    FormulaError,
    parse_formula,
    validate_refs,
)


def ev(text: str, resolve) -> float | None:
    from app.services.scoring import evaluate_formula

    return evaluate_formula(parse_formula(text), resolve)


class TestTokenizer:
    def test_numbers_and_idents(self):
        f = parse_formula("a1 + 2.5 + _x")
        assert [r for r in f.refs] == ["a1", "_x"]  # deduped, order-preserving

    def test_decimal_dot_split(self):
        # 2.5 tokenizes as ONE number even though '.' is not a word char
        assert ev("2.5 * a", lambda k: 2) == 5.0

    def test_unexpected_char(self):
        with pytest.raises(FormulaError, match="unexpected character"):
            parse_formula("a + ة")
        with pytest.raises(FormulaError):
            parse_formula("a @ b")
        with pytest.raises(FormulaError):
            parse_formula("2.")  # dangling dot is not a number

    def test_whitespace_only_is_empty(self):
        with pytest.raises(FormulaError, match="empty"):
            parse_formula("   ")

    def test_length_limit(self):
        parse_formula("a+" * 499 + "11")  # exactly 1000 chars — OK
        with pytest.raises(FormulaError, match="longer than"):
            parse_formula("a+" * 500 + "1")  # 1001 chars


class TestParser:
    def test_empty(self):
        with pytest.raises(FormulaError, match="empty"):
            parse_formula("")

    def test_trailing_tokens(self):
        with pytest.raises(FormulaError):
            parse_formula("a b")
        with pytest.raises(FormulaError):
            parse_formula("(a)(b)")

    def test_unclosed_and_stray(self):
        with pytest.raises(FormulaError, match="expected"):
            parse_formula("(a")
        with pytest.raises(FormulaError):
            parse_formula("a)")

    def test_precedence(self):
        assert ev("2 + 3 * 4", lambda k: 0) == 14
        assert ev("(2 + 3) * 4", lambda k: 0) == 20

    def test_unary(self):
        assert ev("-1 + 3", lambda k: 0) == 2
        assert ev("- -2", lambda k: 0) == 2
        assert ev("+2", lambda k: 0) == 2

    def test_calls(self):
        assert ev("min(3, 1, 2)", lambda k: 0) == 1
        assert ev("max(3, 1, 2)", lambda k: 0) == 3
        assert ev("abs(-5)", lambda k: 0) == 5
        assert ev("max(min(5, 2), 1)", lambda k: 0) == 2

    def test_arity(self):
        with pytest.raises(FormulaError, match="arguments"):
            parse_formula("abs(1, 2)")
        with pytest.raises(FormulaError, match="expected"):
            parse_formula("min()")

    def test_function_name_without_call_is_a_ref(self):
        f = parse_formula("min + 1")
        assert f.refs == ("min",)  # a question named 'min' (KEY_RE allows it)
        assert ev("min + 1", lambda k: 5) == 6

    def test_depth_limit(self):
        # the counter counts FACTORS (expr→term→factor), so n nested parens
        # = depth n+1 — 99 parens pass, 100 raise
        parse_formula("(" * 99 + "1" + ")" * 99)
        with pytest.raises(FormulaError, match="deeply nested"):
            parse_formula("(" * 100 + "1" + ")" * 100)
        assert MAX_DEPTH == 100

    def test_max_formula_length_constant(self):
        assert MAX_FORMULA_LENGTH == 1000


class TestValidateRefs:
    def test_unknown_key(self):
        f = parse_formula("nope + 1")
        with pytest.raises(FormulaError, match="unknown question key"):
            validate_refs(f, {"a": "number"})

    def test_string_question(self):
        f = parse_formula("s + 1")
        with pytest.raises(FormulaError, match="not numeric"):
            validate_refs(f, {"a": "number", "s": "string"})

    def test_choice_is_scorable(self):
        f = parse_formula("c + 1")
        validate_refs(f, {"c": "choice"})  # no raise


class TestEvaluate:
    def test_none_propagates(self):
        assert ev("a + b", lambda k: None) is None
        assert ev("a * b", lambda k: 1 if k == "a" else None) is None
        assert ev("-a", lambda k: None) is None
        assert ev("min(a, b)", lambda k: 1 if k == "a" else None) is None

    def test_division_by_zero_is_none(self):
        assert ev("a / 0", lambda k: 5) is None
        assert ev("a / (1 - 1)", lambda k: 5) is None

    def test_zero_denominator_only_when_exactly_zero(self):
        assert ev("a / b", lambda k: 0.001 if k == "b" else 1) == 1000


def test_mirrored_constants_are_the_ones_the_corpus_tests():
    """Keep these in sync with frontend/src/lib/questionnaire.ts (the parity
    corpus pins the exact boundaries)."""
    from app.services.questionnaires import KEY_RE

    assert KEY_RE.pattern == "^[a-z0-9_]{1,64}$"
