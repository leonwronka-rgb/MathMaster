from __future__ import annotations

import ast
import re
from typing import Final

import sympy as sp

from mathematics.solutions import Exercise
from mathematics.topics import Topic

_FUNCTIONS: Final[dict[str, object]] = {
    "sqrt": sp.sqrt,
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "log": sp.log,
    "ln": sp.log,
    "exp": sp.exp,
    "abs": sp.Abs,
}
_CONSTANTS: Final[dict[str, sp.Basic]] = {"pi": sp.pi, "e": sp.E}
_BINARY_OPERATORS: Final[dict[type[ast.operator], object]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a**b,
}
_UNARY_OPERATORS: Final[dict[type[ast.unaryop], object]] = {
    ast.UAdd: lambda a: a,
    ast.USub: lambda a: -a,
}


class AnswerParseError(ValueError):
    """Odpowiedź zawiera niedozwolony lub niepoprawny zapis."""


def parse_answer(text: str) -> sp.Basic:
    """Parse arithmetic expressions without eval or SymPy's eval-based parser."""
    normalized = (
        text.strip()
        .replace("^", "**")
        .replace("π", "pi")
        .replace("≤", "<=")
        .replace("≥", ">=")
    )
    if not normalized or len(normalized) > 500:
        raise AnswerParseError("Wpisz odpowiedź o długości do 500 znaków.")
    try:
        tree = ast.parse(normalized, mode="eval")
        result = _build_node(tree.body)
    except (SyntaxError, TypeError, ValueError, ZeroDivisionError) as error:
        raise AnswerParseError("Nie można odczytać odpowiedzi matematycznej.") from error
    if not isinstance(result, sp.Basic):
        raise AnswerParseError("Odpowiedź musi być określonym wyrażeniem.")
    if not isinstance(result, sp.Set) and result.has(
        sp.zoo, sp.nan, sp.oo, -sp.oo
    ):
        raise AnswerParseError("Odpowiedź musi być określonym wyrażeniem.")
    return result


def _build_node(node: ast.AST) -> sp.Basic:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise AnswerParseError("Dozwolone są wyłącznie liczby i wyrażenia.")
        if isinstance(node.value, int) and node.value.bit_length() > 4096:
            raise AnswerParseError("Liczba jest zbyt duża.")
        return sp.Rational(str(node.value)) if isinstance(node.value, float) else sp.Integer(node.value)

    if isinstance(node, ast.Name):
        name = node.id.casefold()
        if name in _CONSTANTS:
            return _CONSTANTS[name]
        if len(name) > 1:
            raise AnswerParseError("Niedozwolony symbol.")
        return sp.Symbol(name)

    if isinstance(node, ast.BinOp):
        operator = _BINARY_OPERATORS.get(type(node.op))
        if operator is None:
            raise AnswerParseError("Niedozwolony operator.")
        left, right = _build_node(node.left), _build_node(node.right)
        if isinstance(node.op, ast.Div) and right == 0:
            raise AnswerParseError("Dzielenie przez zero nie jest dozwolone.")
        if isinstance(node.op, ast.Pow) and right.is_Integer:
            exponent = abs(int(right))
            if exponent > 100 or (
                isinstance(left, sp.Integer)
                and int(left).bit_length() * exponent > 20_000
            ):
                raise AnswerParseError("Wykładnik jest zbyt duży.")
        return operator(left, right)  # type: ignore[operator]

    if isinstance(node, ast.UnaryOp):
        operator = _UNARY_OPERATORS.get(type(node.op))
        if operator is None:
            raise AnswerParseError("Niedozwolony operator.")
        return operator(_build_node(node.operand))  # type: ignore[operator]

    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        left, right = _build_node(node.left), _build_node(node.comparators[0])
        relation = type(node.ops[0])
        if right == sp.Symbol("x") and left.is_real is True and not left.free_symbols:
            left, right = right, left
            relation = {
                ast.Lt: ast.Gt,
                ast.LtE: ast.GtE,
                ast.Gt: ast.Lt,
                ast.GtE: ast.LtE,
            }.get(relation, relation)
        if (
            left == sp.Symbol("x")
            and right.is_real is True
            and right.is_finite is True
            and not right.free_symbols
        ):
            if relation in (ast.Lt, ast.LtE):
                return sp.Interval(-sp.oo, right, right_open=relation is ast.Lt)
            if relation in (ast.Gt, ast.GtE):
                return sp.Interval(right, sp.oo, left_open=relation is ast.Gt)
        raise AnswerParseError("Obsługiwane są tylko nierówności x <, ≤, > lub ≥ liczba.")

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        function = _FUNCTIONS.get(node.func.id.casefold())
        if function is None or node.keywords or len(node.args) != 1:
            raise AnswerParseError("Funkcja jest niedozwolona lub niepoprawna.")
        return function(_build_node(node.args[0]))  # type: ignore[operator]

    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        values = tuple(_build_node(element) for element in node.elts)
        if isinstance(node, ast.Tuple):
            return sp.Tuple(*values)
        return sp.FiniteSet(*values)

    raise AnswerParseError("Niedozwolony zapis odpowiedzi.")


def is_correct_answer(exercise: Exercise, submitted: str | sp.Basic) -> bool:
    try:
        if (
            exercise.topic == Topic.POWERS
            and isinstance(submitted, str)
            and _is_unmodified_power_expression(exercise.prompt, submitted)
        ):
            return False
        candidate = parse_answer(submitted) if isinstance(submitted, str) else submitted
        if not isinstance(candidate, sp.Basic):
            return False
        if exercise.answer_mode == "antiderivative":
            variable = sp.Symbol("x")
            return _equivalent(sp.diff(candidate, variable), sp.diff(exercise.answer, variable))
        return _equivalent(candidate, exercise.answer)
    except (AnswerParseError, TypeError, ValueError, OverflowError):
        return False


def _is_unmodified_power_expression(prompt: str, submitted: str) -> bool:
    match = re.fullmatch(r"\s*Oblicz:\s*(.+?)\.\s*", prompt)
    if match is None:
        return False
    normalize = lambda value: re.sub(r"\s+", "", value).replace("^", "**")
    return normalize(submitted) == normalize(match.group(1))


def _equivalent(candidate: sp.Basic, answer: sp.Basic) -> bool:
    if isinstance(answer, sp.FiniteSet):
        if isinstance(candidate, sp.Tuple):
            candidate = sp.FiniteSet(*candidate)
        elif len(answer) == 1 and not isinstance(candidate, sp.Set):
            return _equivalent(candidate, next(iter(answer)))
    if isinstance(candidate, sp.Tuple) or isinstance(answer, sp.Tuple):
        return (
            isinstance(candidate, sp.Tuple)
            and isinstance(answer, sp.Tuple)
            and len(candidate) == len(answer)
            and all(_equivalent(left, right) for left, right in zip(candidate, answer))
        )
    if isinstance(candidate, sp.Set) or isinstance(answer, sp.Set):
        if not isinstance(candidate, sp.Set) or not isinstance(answer, sp.Set):
            return False
        return candidate == answer or sp.simplify(candidate.symmetric_difference(answer)) == sp.EmptySet
    difference = sp.simplify(candidate - answer)
    if difference == 0 or difference.is_zero is True:
        return True
    if difference.free_symbols:
        return False
    try:
        return bool(
            candidate.is_real
            and answer.is_real
            and abs(float(sp.N(difference, 30))) <= 1e-9
        )
    except (TypeError, ValueError, OverflowError):
        return False


def validate_answer(exercise: Exercise, submitted: str | sp.Basic) -> bool:
    return is_correct_answer(exercise, submitted)
