from __future__ import annotations

import math
import random

import sympy as sp

from mathematics.generators import ExerciseGenerator
from mathematics.solutions import Exercise
from mathematics.topics import DIFFICULTY_LEVELS, TOPICS, Topic
from mathematics.validators import is_correct_answer, parse_answer

X = sp.Symbol("x")


class MathEngine:
    """Silnik obliczeń symbolicznych, generator zadań i weryfikator odpowiedzi."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.generator = ExerciseGenerator(rng)

    @property
    def topics(self) -> tuple[Topic, ...]:
        return TOPICS

    @property
    def difficulty_levels(self) -> tuple[int, ...]:
        return DIFFICULTY_LEVELS

    def generate(
        self, topic: Topic | str, difficulty: int = 1
    ) -> Exercise:
        return self.generator.generate(topic, difficulty)

    @staticmethod
    def check_answer(exercise: Exercise, submitted: str | sp.Basic) -> bool:
        return is_correct_answer(exercise, submitted)

    @staticmethod
    def simplify(expression: str | sp.Basic) -> sp.Basic:
        parsed = parse_answer(expression) if isinstance(expression, str) else expression
        if not isinstance(parsed, sp.Basic):
            raise TypeError("Wyrażenie musi być symbolem lub tekstem.")
        return sp.simplify(parsed)

    @staticmethod
    def solve_equation(
        left: str | sp.Basic, right: str | sp.Basic = "0", variable: str = "x"
    ) -> sp.Set:
        symbol = MathEngine._symbol(variable)
        lhs = parse_answer(left) if isinstance(left, str) else left
        rhs = parse_answer(right) if isinstance(right, str) else right
        if not isinstance(lhs, sp.Basic) or not isinstance(rhs, sp.Basic):
            raise TypeError("Strony równania muszą być wyrażeniami.")
        return sp.solveset(lhs - rhs, symbol, domain=sp.S.Complexes)

    @staticmethod
    def solve_system(
        equations: tuple[str | sp.Basic, ...],
        variables: tuple[str, ...] = ("x", "y"),
    ) -> tuple[sp.Basic, ...]:
        if not equations or len(equations) != len(variables):
            raise ValueError("Układ musi zawierać tyle równań co zmiennych.")
        symbols = tuple(MathEngine._symbol(name) for name in variables)
        expressions = tuple(
            parse_answer(item) if isinstance(item, str) else item
            for item in equations
        )
        if not all(isinstance(item, sp.Basic) for item in expressions):
            raise TypeError("Równania muszą być wyrażeniami.")
        solutions = sp.solve(expressions, symbols, dict=True)
        if len(solutions) != 1 or any(symbol not in solutions[0] for symbol in symbols):
            raise ValueError("Układ nie ma dokładnie jednego rozwiązania.")
        solution = solutions[0]
        return tuple(sp.simplify(solution[symbol]) for symbol in symbols)

    @staticmethod
    def derivative(expression: str | sp.Basic, variable: str = "x") -> sp.Basic:
        parsed = MathEngine._expression(expression)
        symbol = MathEngine._symbol(variable)
        return sp.diff(parsed, symbol)

    @staticmethod
    def integral(expression: str | sp.Basic, variable: str = "x") -> sp.Basic:
        parsed = MathEngine._expression(expression)
        symbol = MathEngine._symbol(variable)
        return sp.integrate(parsed, symbol)

    @staticmethod
    def limit(
        expression: str | sp.Basic, point: str | sp.Basic, variable: str = "x"
    ) -> sp.Basic:
        parsed = MathEngine._expression(expression)
        target = parse_answer(point) if isinstance(point, str) else point
        if not isinstance(target, sp.Basic):
            raise TypeError("Punkt granicy musi być wyrażeniem.")
        return sp.limit(parsed, MathEngine._symbol(variable), target)

    @staticmethod
    def function_samples(
        expression: str | sp.Basic,
        start: float,
        end: float,
        samples: int = 200,
    ) -> tuple[tuple[float, float], ...]:
        if not math.isfinite(start) or not math.isfinite(end) or start >= end:
            raise ValueError("Zakres wykresu musi być skończony i rosnący.")
        if not 2 <= samples <= 10_000:
            raise ValueError("Liczba próbek musi należeć do zakresu 2–10000.")
        parsed = MathEngine._expression(expression)
        if parsed.free_symbols - {X}:
            raise ValueError("Funkcja może zawierać wyłącznie zmienną x.")
        points: list[tuple[float, float]] = []
        for index in range(samples):
            x_value = start + (end - start) * index / (samples - 1)
            try:
                y_value = float(sp.N(parsed.subs(X, x_value), 15))
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(y_value):
                points.append((x_value, y_value))
        if len(points) < 2:
            raise ValueError("Nie udało się wyznaczyć wystarczającej liczby punktów wykresu.")
        return tuple(points)

    @staticmethod
    def _expression(value: str | sp.Basic) -> sp.Basic:
        result = parse_answer(value) if isinstance(value, str) else value
        if not isinstance(result, sp.Basic):
            raise TypeError("Wartość musi być wyrażeniem symbolicznym.")
        return result

    @staticmethod
    def _symbol(name: str) -> sp.Symbol:
        if len(name) != 1 or not name.isalpha():
            raise ValueError("Nazwa zmiennej musi być pojedynczą literą.")
        return sp.Symbol(name)


def generate_exercise(
    topic: Topic | str,
    difficulty: int = 1,
    *,
    rng: random.Random | None = None,
) -> Exercise:
    return MathEngine(rng).generate(topic, difficulty)
