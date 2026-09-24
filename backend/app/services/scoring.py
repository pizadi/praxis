"""Score-formula parser + evaluator for questionnaire templates.

A formula is a small arithmetic expression over question keys:

    expr   := term (("+" | "-") term)*
    term   := factor (("*" | "/") factor)*
    factor := NUMBER | KEY | FUNC "(" expr ("," expr)* ")"
            | ("+" | "-") factor | "(" expr ")"

`KEY` is a question key ([a-z0-9_]+); it resolves to the answered numeric
value (number question) or the chosen option's score (choice question).
Functions: `min`/`max` (1+ arguments) and `abs` (exactly one argument).

Syntax/semantic validation happens once at template save (parse_formula +
validate_refs, funneled through the format validation); evaluation is total
and never raises: any unresolvable operand (missing/invalid answer, chosen
option without a score) or division by zero makes the whole result None —
a missing score is never invented.

This module is mirrored client-side in frontend/src/lib/questionnaire.ts
(keep the two in sync).
"""

from __future__ import annotations

import re
import typing as t
from dataclasses import dataclass

MAX_FORMULA_LENGTH = 1000
MAX_DEPTH = 100

# name -> (min arity, max arity or None for unbounded)
FUNCTIONS: dict[str, tuple[int, int | None]] = {
    "min": (1, None),
    "max": (1, None),
    "abs": (1, 1),
}

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_DOT_NUM_RE = re.compile(r"\.\d+")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_OPS = frozenset("+-*/(),")
_TOKEN = tuple[str, float] | tuple[str, str]


class FormulaError(ValueError):
    """Formula syntax/semantic error (client-facing; becomes a 422)."""


@dataclass(frozen=True)
class Num:
    value: float


@dataclass(frozen=True)
class Ref:
    key: str


@dataclass(frozen=True)
class UnOp:
    op: str  # "-" | "+"
    operand: Node


@dataclass(frozen=True)
class BinOp:
    op: str  # "+" | "-" | "*" | "/"
    left: Node
    right: Node


@dataclass(frozen=True)
class Call:
    name: str
    args: t.Sequence[Node]


Node = Num | Ref | UnOp | BinOp | Call


@dataclass(frozen=True)
class Formula:
    """Parsed formula: AST plus the question keys it references (in order)."""

    text: str
    ast: Node
    refs: tuple[str, ...]


# --- tokenizer -------------------------------------------------------------------


def _tokenize(text: str) -> list[_TOKEN]:
    tokens: list[_TOKEN] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in _OPS:
            tokens.append(("op", ch))
            i += 1
            continue
        m = _WORD_RE.match(text, i)
        if m is None:
            raise FormulaError(f"unexpected character {ch!r} at position {i + 1}")
        word = m.group(0)
        i = m.end()
        # decimal literal like 2.5 — the dot is not a word character
        if word.isdigit() and i + 1 < n and text[i] == "." and text[i + 1].isdigit():
            m2 = _DOT_NUM_RE.match(text, i)
            assert m2 is not None  # next char is a digit by the check above
            word += m2.group(0)
            i = m2.end()
        if _NUM_RE.fullmatch(word):
            tokens.append(("num", float(word)))
        else:
            tokens.append(("ident", word))
    return tokens


# --- parser ------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[_TOKEN]) -> None:
        self._toks = tokens
        self._pos = 0
        self._depth = 0

    def _peek(self) -> _TOKEN | None:
        return self._toks[self._pos] if self._pos < len(self._toks) else None

    def _expect_op(self, op: str) -> None:
        tok = self._peek()
        if tok is None or tok != ("op", op):
            raise FormulaError(f"expected {op!r}")
        self._pos += 1

    def parse(self) -> Node:
        if not self._toks:
            raise FormulaError("formula is empty")
        node = self._expr()
        if self._pos != len(self._toks):
            raise FormulaError("unexpected trailing tokens")
        return node

    def _expr(self) -> Node:
        node = self._term()
        while (tok := self._peek()) == ("op", "+") or tok == ("op", "-"):
            self._pos += 1
            node = BinOp(op=str(tok[1]), left=node, right=self._term())
        return node

    def _term(self) -> Node:
        node = self._factor()
        while (tok := self._peek()) == ("op", "*") or tok == ("op", "/"):
            self._pos += 1
            node = BinOp(op=str(tok[1]), left=node, right=self._factor())
        return node

    def _factor(self) -> Node:
        self._depth += 1
        if self._depth > MAX_DEPTH:
            raise FormulaError("formula is too deeply nested")
        try:
            tok = self._peek()
            if tok is None:
                raise FormulaError("unexpected end of formula")
            kind, val = tok
            if kind == "num":
                self._pos += 1
                return Num(float(val))
            if kind == "op" and val == "(":
                self._pos += 1
                node = self._expr()
                self._expect_op(")")
                return node
            if kind == "op" and val in ("+", "-"):
                self._pos += 1
                return UnOp(op=val, operand=self._factor())
            if kind == "ident":
                self._pos += 1
                if val in FUNCTIONS and self._peek() == ("op", "("):
                    return self._call(str(val))
                return Ref(key=str(val))
            raise FormulaError(f"unexpected token {val!r}")
        finally:
            self._depth -= 1

    def _call(self, name: str) -> Call:
        self._expect_op("(")
        args = [self._expr()]
        while self._peek() == ("op", ","):
            self._pos += 1
            args.append(self._expr())
        self._expect_op(")")
        low, high = FUNCTIONS[name]
        if len(args) < low or (high is not None and len(args) > high):
            raise FormulaError(f"wrong number of arguments for {name}()")
        return Call(name=name, args=args)


def _collect_refs(node: Node, out: list[str]) -> None:
    if isinstance(node, Ref):
        out.append(node.key)
    elif isinstance(node, UnOp):
        _collect_refs(node.operand, out)
    elif isinstance(node, BinOp):
        _collect_refs(node.left, out)
        _collect_refs(node.right, out)
    elif isinstance(node, Call):
        for a in node.args:
            _collect_refs(a, out)


def parse_formula(text: str) -> Formula:
    """Parse a formula expression; raises FormulaError on any syntax error."""
    if len(text) > MAX_FORMULA_LENGTH:
        raise FormulaError(f"formula longer than {MAX_FORMULA_LENGTH} characters")
    ast = _Parser(_tokenize(text)).parse()
    refs: list[str] = []
    _collect_refs(ast, refs)
    return Formula(text=text, ast=ast, refs=tuple(dict.fromkeys(refs)))


def validate_refs(formula: Formula, key_types: dict[str, str]) -> None:
    """All referenced keys must exist and be number/choice questions."""
    for key in formula.refs:
        qtype = key_types.get(key)
        if qtype is None:
            raise FormulaError(f"unknown question key: {key}")
        if qtype not in ("number", "choice"):
            raise FormulaError(
                f"question {key} is not numeric (string questions cannot be scored)"
            )


def validate_formula_for_questions(text: str, questions: dict[str, str]) -> Formula:
    """Parse and semantically validate a formula against question key types.

    This is the one server-side entry point used by both full format
    validation and the builder's dedicated live-check endpoint.
    """
    formula = parse_formula(text)
    validate_refs(formula, questions)
    return formula



# --- evaluation ---------------------------------------------------------------------


def evaluate_formula(
    formula: Formula, resolve: t.Callable[[str], float | None]
) -> float | None:
    """Evaluate the AST; None whenever any operand is unresolvable."""

    def ev(node: Node) -> float | None:
        if isinstance(node, Num):
            return node.value
        if isinstance(node, Ref):
            return resolve(node.key)
        if isinstance(node, UnOp):
            v = ev(node.operand)
            if v is None:
                return None
            return -v if node.op == "-" else v
        if isinstance(node, BinOp):
            left = ev(node.left)
            right = ev(node.right)
            if left is None or right is None:
                return None
            if node.op == "+":
                return left + right
            if node.op == "-":
                return left - right
            if node.op == "*":
                return left * right
            if right == 0:
                return None  # division by zero -> score not computable
            return left / right
        if isinstance(node, Call):
            vals: list[float] = []
            for a in node.args:
                v = ev(a)
                if v is None:
                    return None
                vals.append(v)
            if node.name == "abs":
                return abs(vals[0])
            return min(vals) if node.name == "min" else max(vals)
        raise AssertionError(f"unreachable node {node!r}")  # pragma: no cover

    return ev(formula.ast)
