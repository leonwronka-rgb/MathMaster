from __future__ import annotations

import re
from dataclasses import dataclass

import sympy as sp

from mathematics.validators import AnswerParseError, parse_answer

_X = sp.Symbol("x")


class AssistantInputError(ValueError):
    """The submitted problem could not be read as a supported exercise."""


class UnsupportedProblemError(AssistantInputError):
    """The assistant recognized a problem type it does not solve yet."""


@dataclass(frozen=True, slots=True)
class SolutionStep:
    title: str
    explanation: str
    equation: str


@dataclass(frozen=True, slots=True)
class Explanation:
    task_type: str
    original_problem: str
    answer: sp.Basic
    steps: tuple[SolutionStep, ...]
    verified: bool
    verification_text: str
    common_mistakes: tuple[str, ...]


class MathAssistantService:
    def explain(self, problem: str) -> Explanation:
        normalized_problem = problem.strip()
        if not normalized_problem:
            raise AssistantInputError("Wpisz równanie, które chcesz rozwiązać.")
        if len(normalized_problem) > 500:
            raise AssistantInputError("Treść zadania może mieć maksymalnie 500 znaków.")
        if normalized_problem.count("=") != 1:
            raise UnsupportedProblemError(
                "Nie rozpoznano równania liniowego. Wpisz jedno równanie, "
                "na przykład 2x + 6 = 14."
            )

        left_text, right_text = normalized_problem.split("=", maxsplit=1)
        if not left_text.strip() or not right_text.strip():
            raise AssistantInputError("Podaj wyrażenie po obu stronach znaku równości.")
        try:
            left = parse_answer(self._normalize_side(left_text))
            right = parse_answer(self._normalize_side(right_text))
        except AnswerParseError as error:
            raise AssistantInputError(
                "Nie można odczytać równania. Użyj liczb, x oraz działań +, −, ×, ÷ i potęg."
            ) from error

        if (left.free_symbols | right.free_symbols) - {_X}:
            raise UnsupportedProblemError(
                "Rozpoznano równanie ze zmiennymi, ale asystent obsługuje obecnie "
                "tylko równania liniowe z jedną niewiadomą x."
            )
        try:
            left_polynomial = sp.Poly(left, _X)
            right_polynomial = sp.Poly(right, _X)
        except sp.PolynomialError as error:
            raise UnsupportedProblemError(
                "To równanie nie jest wielomianowe. Asystent obsługuje obecnie "
                "tylko równania liniowe z jedną niewiadomą x."
            ) from error
        if max(left_polynomial.degree(), right_polynomial.degree()) > 1:
            degree = max(left_polynomial.degree(), right_polynomial.degree())
            raise UnsupportedProblemError(
                f"Rozpoznano równanie wielomianowe stopnia {degree}, ale asystent "
                "obsługuje obecnie tylko równania liniowe."
            )

        left_x = sp.simplify(left_polynomial.coeff_monomial(_X))
        left_constant = sp.simplify(left_polynomial.coeff_monomial(1))
        right_x = sp.simplify(right_polynomial.coeff_monomial(_X))
        right_constant = sp.simplify(right_polynomial.coeff_monomial(1))
        coefficient = sp.simplify(left_x - right_x)
        constant = sp.simplify(right_constant - left_constant)
        if coefficient == 0:
            raise UnsupportedProblemError(
                "To równanie nie ma jednego wyznaczonego rozwiązania. "
                "Asystent pokazuje obecnie rozwiązania równań liniowych z jednym wynikiem."
            )

        steps = [
            SolutionStep(
                "Rozpoznaj równanie liniowe",
                "Po obu stronach występuje najwyżej pierwsza potęga x. "
                "Dla a₁x + b₁ = a₂x + b₂ odejmujemy wyrazy podobne: "
                "(a₁ − a₂)x = b₂ − b₁.",
                f"{sp.sstr(left)} = {sp.sstr(right)}",
            )
        ]
        left_after_constants = sp.simplify(left - left_constant)
        right_after_constants = sp.simplify(right - left_constant)
        if left_constant != 0:
            action = self._operation_title(left_constant)
            steps.append(
                SolutionStep(
                    action,
                    f"Wykonujemy tę samą operację po obu stronach, aby zachować równość. "
                    f"Usuwamy stały składnik {sp.sstr(left_constant)} z lewej strony.",
                    f"{sp.sstr(left_after_constants)} = {sp.sstr(right_after_constants)}",
                )
            )

        left_after_variables = sp.simplify(left_after_constants - right_x * _X)
        right_after_variables = sp.simplify(right_after_constants - right_x * _X)
        if right_x != 0:
            action = self._operation_title(right_x, _X)
            steps.append(
                SolutionStep(
                    action,
                    f"Wykonujemy tę samą operację po obu stronach, aby wszystkie "
                    f"wyrazy z x znalazły się po lewej. Usuwamy składnik "
                    f"{sp.sstr(right_x * _X)} z prawej strony.",
                    f"{sp.sstr(left_after_variables)} = {sp.sstr(right_after_variables)}",
                )
            )

        answer = sp.simplify(constant / coefficient)
        steps.append(
            SolutionStep(
                f"Podziel obie strony przez {sp.sstr(coefficient)}",
                f"Dzielimy całe równanie przez współczynnik stojący przy x, "
                f"{sp.sstr(coefficient)}, aby pozostawić samo x.",
                f"x = {sp.sstr(answer)}",
            )
        )
        left_value = sp.simplify(left.subs(_X, answer))
        right_value = sp.simplify(right.subs(_X, answer))
        verified = sp.simplify(left_value - right_value) == 0
        if not verified:
            raise ArithmeticError(
                "Weryfikacja SymPy nie potwierdziła rozwiązania równania."
            )
        verification_text = (
            f"Po podstawieniu x = {sp.sstr(answer)}: "
            f"lewa strona = {sp.sstr(left_value)}, "
            f"prawa strona = {sp.sstr(right_value)}. Strony są równe."
        )
        steps.append(
            SolutionStep(
                "Sprawdź wynik przez podstawienie",
                verification_text,
                f"{sp.sstr(left_value)} = {sp.sstr(right_value)}  ✓",
            )
        )
        return Explanation(
            task_type="Równanie liniowe",
            original_problem=normalized_problem,
            answer=answer,
            steps=tuple(steps),
            verified=verified,
            verification_text=verification_text,
            common_mistakes=(
                "Nie zmieniaj znaku składnika bez wykonania tej samej operacji po obu stronach równania.",
                "Dziel całe obie strony przez współczynnik przy x, a nie tylko jeden składnik.",
                "Po obliczeniu podstaw wynik do równania wyjściowego, nie tylko do jednego z przekształconych wierszy.",
            ),
        )

    @staticmethod
    def _normalize_side(text: str) -> str:
        normalized = text.replace("×", "*").replace("·", "*").replace("−", "-")
        normalized = normalized.replace("÷", "/").replace("π", "pi")
        normalized = re.sub(
            r"(\d)\s*(?=(?:x|pi)\b)", r"\1*", normalized, flags=re.IGNORECASE
        )
        normalized = re.sub(r"(\d)\s*(?=\()", r"\1*", normalized)
        normalized = re.sub(r"([xX])\s*(?=\()", r"\1*", normalized)
        normalized = re.sub(
            r"\)\s*(?=(?:\d|[xX]\b|pi\b|\())",
            ")*",
            normalized,
            flags=re.IGNORECASE,
        )
        return normalized

    @staticmethod
    def _operation_title(value: sp.Basic, variable: sp.Symbol | None = None) -> str:
        term = value * variable if variable is not None else value
        if value.is_negative is True:
            magnitude = -term
            return f"Dodaj {sp.sstr(magnitude)} do obu stron"
        if value.is_positive is True:
            return f"Odejmij {sp.sstr(term)} od obu stron"
        return f"Odejmij ({sp.sstr(term)}) od obu stron"
