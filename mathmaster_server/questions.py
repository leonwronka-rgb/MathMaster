from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass
from fractions import Fraction

from mathmaster_server.schemas import MatchSettings


@dataclass(frozen=True, slots=True)
class Question:
    question_id: str
    topic: str
    prompt: str
    answer: str

    def public(self, number: int, count: int, remaining_seconds: int) -> dict[str, object]:
        return {
            "question_id": self.question_id,
            "prompt": self.prompt,
            "question_number": number,
            "question_count": count,
            "remaining_seconds": remaining_seconds,
        }


SUPPORTED_TOPICS = {
    "addition", "subtraction", "multiplication", "division", "order_of_operations",
    "fraction_simplify", "fraction_expand", "fraction_addition", "fraction_subtraction",
    "fraction_multiplication", "fraction_division",
    "percent_of", "percent_increase", "percent_decrease", "percent_original",
    "algebra_expression", "linear_equation", "linear_inequality", "linear_system",
    "quadratic_equation",
    "area", "perimeter", "volume", "surface_area", "pythagorean", "analytic_geometry",
    "powers", "square_roots", "function_value", "graph_point", "sequences",
    "trigonometry", "logarithms", "combinatorics", "probability", "statistics",
    "limits", "derivatives", "integrals",
}


def generate_question(settings: MatchSettings) -> Question:
    candidates = [topic for topic in settings.topics if topic in SUPPORTED_TOPICS]
    if not candidates:
        raise ValueError("Selected topics are not yet supported by the server question bank.")
    topic = random.choice(candidates)
    level = settings.difficulty
    low, high = (1, 10) if level < 3 else (5, 40) if level < 5 else (10, 100)

    if topic == "addition":
        a, b = random.randint(low, high), random.randint(low, high)
        prompt, answer = f"Oblicz: {a} + {b}", str(a + b)
    elif topic == "subtraction":
        a, b = sorted((random.randint(low, high), random.randint(low, high)), reverse=True)
        prompt, answer = f"Oblicz: {a} - {b}", str(a - b)
    elif topic == "multiplication":
        a, b = random.randint(low, high), random.randint(low, max(2, high // 3))
        prompt, answer = f"Oblicz: {a} × {b}", str(a * b)
    elif topic == "division":
        b, answer_number = random.randint(2, max(3, high // 2)), random.randint(low, high)
        prompt, answer = f"Oblicz: {b * answer_number} ÷ {b}", str(answer_number)
    elif topic == "order_of_operations":
        a, b, c = random.randint(2, 15), random.randint(2, 12), random.randint(1, 30)
        prompt, answer = f"Oblicz: {a} + {b} × {c}", str(a + b * c)
    elif topic == "fraction_simplify":
        numerator, denominator, factor = random.randint(1, 9), random.randint(2, 12), random.randint(2, 8)
        fraction = Fraction(numerator * factor, denominator * factor)
        prompt = f"Skróć ułamek: {fraction.numerator}/{fraction.denominator}."
        answer = _fraction_text(fraction)
    elif topic == "fraction_expand":
        numerator, denominator, factor = random.randint(1, 9), random.randint(2, 12), random.randint(2, 8)
        prompt, answer = (
            f"Rozszerz ułamek {numerator}/{denominator} przez {factor}.",
            f"{numerator * factor}/{denominator * factor}",
        )
    elif topic.startswith("fraction_"):
        a, b = random.randint(1, 9), random.randint(2, 12)
        c, d = random.randint(1, 9), random.randint(2, 12)
        left, right = Fraction(a, b), Fraction(c, d)
        operator = {
            "fraction_addition": ("+", left + right),
            "fraction_subtraction": ("−", left - right),
            "fraction_multiplication": ("×", left * right),
            "fraction_division": ("÷", left / right),
        }.get(topic)
        if operator is None:
            raise ValueError("Unsupported fraction topic.")
        prompt = f"Oblicz: {a}/{b} {operator[0]} {c}/{d}"
        answer = _fraction_text(operator[1])
    elif topic == "percent_of":
        percent = random.choice((5, 10, 15, 20, 25, 30, 40, 50, 75))
        number = random.choice((40, 60, 80, 100, 120, 160, 200, 240))
        prompt, answer = f"Oblicz {percent}% liczby {number}.", _fraction_text(Fraction(percent * number, 100))
    elif topic in {"percent_increase", "percent_decrease"}:
        original = random.choice((80, 100, 120, 160, 200, 240))
        percent = random.choice((5, 10, 15, 20, 25))
        factor = 100 + percent if topic == "percent_increase" else 100 - percent
        verb = "podwyżce" if topic == "percent_increase" else "obniżce"
        prompt = f"Cena {original} zł po {verb} o {percent}% wynosi:"
        answer = _fraction_text(Fraction(original * factor, 100))
    elif topic == "percent_original":
        original = random.choice((80, 100, 120, 160, 200))
        percent = random.choice((10, 20, 25))
        discounted = Fraction(original * (100 - percent), 100)
        prompt = f"Po obniżce o {percent}% cena wynosi {_fraction_text(discounted)} zł. Jaka była cena początkowa?"
        answer = str(original)
    elif topic == "algebra_expression":
        a, b, x = random.randint(2, 9), random.randint(-12, 12), random.randint(-8, 8)
        prompt, answer = f"Oblicz wartość wyrażenia {a}x + ({b}) dla x={x}.", str(a * x + b)
    elif topic == "linear_equation":
        x, a = random.randint(-12, 20), random.randint(2, 10)
        b = random.randint(-20, 20)
        prompt, answer = f"Rozwiąż równanie: {a}x + {b} = {a * x + b}", str(x)
    elif topic == "linear_inequality":
        a, boundary, offset = random.randint(2, 8), random.randint(-10, 10), random.randint(1, 15)
        right = a * boundary + offset
        prompt, answer = f"Jaka jest największa liczba całkowita x spełniająca {a}x + {offset} ≤ {right}?", str(boundary)
    elif topic == "linear_system":
        x, y = random.randint(-8, 8), random.randint(-8, 8)
        a, b, c, d = 2, 1, 1, 3
        prompt = (
            f"Rozwiąż układ: {a}x + {b}y = {a*x+b*y}, "
            f"{c}x + {d}y = {c*x+d*y}. Podaj x + y."
        )
        answer = str(x + y)
    elif topic == "quadratic_equation":
        first, second = random.sample(range(-8, 9), 2)
        prompt = f"Podaj większy pierwiastek równania x² - ({first + second})x + ({first * second}) = 0."
        answer = str(max(first, second))
    elif topic == "area":
        shape = random.choice(("prostokąta", "równoległoboku", "rombu", "trapezu"))
        a, b = random.randint(3, 30), random.randint(3, 30)
        if shape == "rombu":
            a, b = 2 * a, 2 * b
            area = Fraction(a * b, 2)
            prompt = f"Oblicz pole rombu o przekątnych {a} i {b}."
            answer = _fraction_text(area)
        elif shape == "trapezu":
            other_base = random.randint(3, 30)
            area = Fraction((a + other_base) * b, 2)
            prompt = f"Oblicz pole trapezu o podstawach {a} i {other_base} oraz wysokości {b}."
            answer = _fraction_text(area)
        else:
            prompt = f"Pole {shape} o podstawie {a} i wysokości {b} wynosi:"
            answer = str(a * b)
    elif topic == "perimeter":
        a, b = random.randint(3, 30), random.randint(3, 30)
        shape = random.choice(("prostokąta", "równoległoboku", "rombu", "trapezu równoramiennego"))
        if shape == "rombu":
            prompt, answer = f"Obwód rombu o boku {a} wynosi:", str(4 * a)
        elif shape == "trapezu równoramiennego":
            prompt, answer = f"Trapez równoramienny ma podstawy {a} i {3*a} oraz ramiona {b}. Oblicz obwód.", str(4 * a + 2 * b)
        else:
            prompt, answer = f"Obwód {shape} o bokach {a} i {b} wynosi:", str(2 * (a + b))
    elif topic == "volume":
        a, b, c = random.randint(2, 15), random.randint(2, 15), random.randint(2, 15)
        prompt, answer = f"Oblicz objętość prostopadłościanu o wymiarach {a}, {b} i {c}.", str(a * b * c)
    elif topic == "surface_area":
        a, b, c = random.randint(2, 12), random.randint(2, 12), random.randint(2, 12)
        prompt, answer = (
            f"Oblicz pole powierzchni prostopadłościanu o wymiarach {a}, {b} i {c}.",
            str(2 * (a * b + b * c + a * c)),
        )
    elif topic == "powers":
        base, power = random.randint(2, 9), random.randint(2, 4)
        prompt, answer = f"Oblicz: {base}^{power}", str(base**power)
    elif topic == "square_roots":
        root = random.randint(2, 30)
        prompt, answer = f"Oblicz: √{root * root}", str(root)
    elif topic == "function_value":
        slope, intercept, x = random.randint(-8, 8), random.randint(-15, 15), random.randint(-10, 10)
        prompt, answer = f"Dla f(x) = {slope}x + ({intercept}), oblicz f({x}).", str(slope * x + intercept)
    elif topic == "graph_point":
        slope, intercept, x = random.randint(-8, 8), random.randint(-15, 15), random.randint(-10, 10)
        prompt = f"Punkt (x, y) leży na wykresie y={slope}x+({intercept}). Dla x={x}, podaj y."
        answer = str(slope * x + intercept)
    elif topic == "sequences":
        first, step, n = random.randint(-5, 15), random.randint(1, 8), random.randint(5, 12)
        prompt, answer = f"Ciąg arytmetyczny ma a₁={first}, r={step}. Oblicz aₙ dla n={n}.", str(first + (n - 1) * step)
    elif topic == "statistics":
        values = sorted(random.randint(1, 30) for _ in range(5))
        prompt, answer = f"Oblicz medianę liczb: {', '.join(map(str, values))}.", str(values[2])
    elif topic == "pythagorean":
        triples = ((3, 4, 5), (5, 12, 13), (8, 15, 17), (7, 24, 25))
        a, b, c = random.choice(triples)
        prompt, answer = f"Trójkąt prostokątny ma przyprostokątne {a} i {b}. Oblicz przeciwprostokątną.", str(c)
    elif topic == "analytic_geometry":
        triples = ((3, 4), (5, 12), (8, 15), (7, 24))
        dx, dy = random.choice(triples)
        prompt = f"Oblicz odległość między punktami (0, 0) i ({dx}, {dy})."
        answer = str(int((dx**2 + dy**2) ** 0.5))
    elif topic == "trigonometry":
        prompt, answer = random.choice((
            ("Oblicz sin(30°).", "1/2"),
            ("Oblicz cos(60°).", "1/2"),
            ("Oblicz tan(45°).", "1"),
        ))
    elif topic == "logarithms":
        base, power = random.choice(((2, 5), (3, 4), (5, 3), (10, 2)))
        prompt, answer = f"Oblicz log_{base}({base**power}).", str(power)
    elif topic == "combinatorics":
        n = random.randint(5, 20)
        prompt, answer = f"Ile jest sposobów wyboru 2 osób z grupy {n} osób?", str(n * (n - 1) // 2)
    elif topic == "probability":
        favorable = random.randint(1, 5)
        prompt = f"Rzucamy uczciwą kostką. Jakie jest prawdopodobieństwo wyrzucenia jednej z {favorable} wybranych ścian?"
        answer = _fraction_text(Fraction(favorable, 6))
    elif topic == "limits":
        point = random.randint(-8, 8)
        prompt, answer = f"Oblicz lim(x→{point}) x².", str(point * point)
    elif topic == "derivatives":
        point, linear = random.randint(-8, 8), random.randint(-10, 10)
        prompt = f"Dla f(x)=x²+({linear})x oblicz f'({point})."
        answer = str(2 * point + linear)
    elif topic == "integrals":
        upper, linear = random.randint(2, 12), random.randint(-5, 5)
        prompt = f"Oblicz całkę oznaczoną ∫₀^{upper} (2x + ({linear})) dx."
        answer = str(upper * upper + linear * upper)
    else:
        raise ValueError("Unsupported topic.")

    return Question(str(uuid.uuid4()), topic, prompt, answer)


def answers_equal(submitted: str, expected: str) -> bool:
    left = _normal_number(submitted)
    right = _normal_number(expected)
    return left is not None and left == right


def _normal_number(value: str) -> Fraction | None:
    value = value.strip().replace(",", ".")
    if not value or len(value) > 80 or not re.fullmatch(r"[+\-]?\d+(?:\.\d+)?(?:/[+\-]?\d+)?", value):
        return None
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            return Fraction(numerator) / Fraction(denominator)
        if "." in value:
            return Fraction(value)
        return Fraction(int(value))
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"

