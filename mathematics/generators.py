from __future__ import annotations

import math
import random

import sympy as sp

from mathematics.solutions import Exercise, describe_solution
from mathematics.topics import DIFFICULTY_LEVELS, Topic

X, Y = sp.symbols("x y")
_TRIG_VALUES = (
    (0, sp.Integer(0), sp.Integer(1), sp.Integer(0)),
    (30, sp.Rational(1, 2), sp.sqrt(3) / 2, sp.sqrt(3) / 3),
    (45, sp.sqrt(2) / 2, sp.sqrt(2) / 2, sp.Integer(1)),
    (60, sp.sqrt(3) / 2, sp.Rational(1, 2), sp.sqrt(3)),
    (90, sp.Integer(1), sp.Integer(0), None),
)


class ExerciseGenerator:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def generate(self, topic: Topic | str, difficulty: int) -> Exercise:
        try:
            selected = Topic(topic)
        except ValueError as error:
            raise ValueError(f"Nieznany temat: {topic!r}.") from error
        if difficulty not in DIFFICULTY_LEVELS:
            raise ValueError("Poziom trudności musi być liczbą od 1 do 5.")
        handler = getattr(self, f"_generate_{selected.value}", None)
        if handler is None:
            raise ValueError(f"Brak generatora dla tematu {selected.value!r}.")
        exercise = handler(difficulty)
        if exercise.topic != selected or exercise.difficulty != difficulty:
            raise RuntimeError("Generator zwrócił zadanie o niezgodnych parametrach.")
        return exercise

    def _integer(self, difficulty: int, *, positive: bool = False) -> int:
        low = 1 if positive else -(10 ** (difficulty - 1))
        high = 10**difficulty
        return self.rng.randint(low, high)

    def _fraction(self, difficulty: int, *, nonzero: bool = False) -> sp.Rational:
        numerator = self._integer(difficulty)
        denominator = self.rng.randint(1, 4 * difficulty + 3)
        while nonzero and numerator == 0:
            numerator = self._integer(difficulty)
        return sp.Rational(numerator, denominator)

    @staticmethod
    def _exercise(
        topic: Topic,
        difficulty: int,
        prompt: str,
        answer: sp.Basic,
        steps: tuple[str, ...],
        answer_mode: str = "equivalent",
    ) -> Exercise:
        return Exercise(
            topic, difficulty, prompt, answer,
            describe_solution(steps, answer, topic), answer_mode,
        )

    def _generate_addition(self, level: int) -> Exercise:
        a, b = self._integer(level), self._integer(level)
        prompt = self.rng.choice((
            f"Oblicz: {a} + {b}",
            f"Do {a} dołóż {b}. Ile otrzymasz?",
            f"Rano było {a} punktów, a później zdobyto {b}. Podaj łączną liczbę punktów.",
        ))
        return self._exercise(Topic.ADDITION, level, prompt, sp.Integer(a + b), (f"Dodajemy składniki: {a} + {b} = {a + b}.",))

    def _generate_subtraction(self, level: int) -> Exercise:
        a, b = self._integer(level), self._integer(level)
        prompt = self.rng.choice((
            f"Oblicz: {a} − ({b})",
            f"Od {a} odejmij {b}.",
            f"Różnica liczb {a} i {b} wynosi?",
        ))
        return self._exercise(Topic.SUBTRACTION, level, prompt, sp.Integer(a - b), (f"Odejmujemy: {a} − ({b}) = {a - b}.",))

    def _generate_multiplication(self, level: int) -> Exercise:
        a, b = self._integer(level, positive=True), self._integer(level)
        prompts = [
            f"Oblicz: {a} · ({b})",
            f"Oblicz iloczyn {a} i {b}.",
        ]
        if b >= 0:
            prompts.append(f"{a} grup ma po {b} elementów. Ile elementów jest łącznie?")
        prompt = self.rng.choice(prompts)
        return self._exercise(Topic.MULTIPLICATION, level, prompt, sp.Integer(a * b), (f"Mnożymy: {a} · ({b}) = {a * b}.",))

    def _generate_division(self, level: int) -> Exercise:
        divisor = self._integer(level, positive=True)
        quotient = self._integer(level)
        dividend = divisor * quotient
        prompt = self.rng.choice((
            f"Oblicz: {dividend} ÷ {divisor}",
            f"Podziel {dividend} na {divisor} równych części. Ile przypada na część?",
            f"Ile razy liczba {divisor} mieści się w {dividend}?",
        ))
        return self._exercise(Topic.DIVISION, level, prompt, sp.Integer(quotient), (f"Iloraz {dividend} ÷ {divisor} = {quotient}.",))

    def _generate_order_of_operations(self, level: int) -> Exercise:
        a, b, c = (self.rng.randint(1, 9 * level) for _ in range(3))
        variant = self.rng.randrange(3)
        if variant == 0:
            expression, answer = f"{a} + {b} · {c}", a + b * c
            steps = (f"Najpierw mnożenie: {b} · {c} = {b*c}.", f"Następnie dodawanie: {a} + {b*c} = {answer}.")
        elif variant == 1:
            expression, answer = f"({a} + {b}) · {c}", (a + b) * c
            steps = (f"Najpierw nawias: {a} + {b} = {a+b}.", f"Następnie mnożenie: {a+b} · {c} = {answer}.")
        else:
            expression, answer = f"{a} · {b} − {c}", a * b - c
            steps = (f"Najpierw mnożenie: {a} · {b} = {a*b}.", f"Następnie odejmowanie: {a*b} − {c} = {answer}.")
        return self._exercise(Topic.ORDER_OF_OPERATIONS, level, f"Oblicz, zachowując kolejność działań: {expression}", sp.Integer(answer), steps)

    def _generate_fraction_simplify(self, level: int) -> Exercise:
        reduced = sp.Rational(self.rng.randint(1, 6 * level), self.rng.randint(2, 8 * level + 1))
        factor = self.rng.randint(2, 5 * level + 1)
        numerator, denominator = int(reduced.p * factor), int(reduced.q * factor)
        return self._exercise(Topic.FRACTION_SIMPLIFY, level, f"Skróć ułamek {numerator}/{denominator}.", reduced, (f"Podziel licznik i mianownik przez ich NWD, czyli {factor * int(sp.gcd(reduced.p, reduced.q))}.",))

    def _generate_fraction_expand(self, level: int) -> Exercise:
        fraction = self._fraction(level, nonzero=True)
        factor = self.rng.randint(2, 5 * level + 1)
        numerator, denominator = int(fraction.p * factor), int(fraction.q * factor)
        answer = sp.Rational(numerator, denominator)
        return self._exercise(Topic.FRACTION_EXPAND, level, f"Rozszerz ułamek {fraction.p}/{fraction.q} przez {factor}. Podaj nowy licznik i mianownik jako parę.", sp.Tuple(numerator, denominator), (f"Pomnóż licznik i mianownik przez {factor}: ({fraction.p}·{factor}, {fraction.q}·{factor}) = ({numerator}, {denominator}).",))

    def _generate_fraction_addition(self, level: int) -> Exercise:
        return self._fraction_operation(level, Topic.FRACTION_ADDITION, "+")

    def _generate_fraction_subtraction(self, level: int) -> Exercise:
        return self._fraction_operation(level, Topic.FRACTION_SUBTRACTION, "−")

    def _generate_fraction_multiplication(self, level: int) -> Exercise:
        return self._fraction_operation(level, Topic.FRACTION_MULTIPLICATION, "·")

    def _generate_fraction_division(self, level: int) -> Exercise:
        return self._fraction_operation(level, Topic.FRACTION_DIVISION, "÷")

    def _fraction_operation(self, level: int, topic: Topic, operator: str) -> Exercise:
        first, second = self._fraction(level), self._fraction(level, nonzero=True)
        if operator == "+":
            answer, calculation = first + second, f"{first} + {second} = {first + second}"
        elif operator == "−":
            answer, calculation = first - second, f"{first} − {second} = {first - second}"
        elif operator == "·":
            answer, calculation = first * second, f"{first} · {second} = {first * second}"
        else:
            answer, calculation = first / second, f"{first} ÷ {second} = {first / second}"
        return self._exercise(topic, level, f"Oblicz i skróć: {first} {operator} {second}", answer, (f"Sprowadź do wspólnego mianownika lub wykonaj działanie na licznikach: {calculation}.",))

    def _generate_percent_of(self, level: int) -> Exercise:
        percent = self.rng.choice((5, 10, 12, 20, 25, 40, 50, 75))
        amount = self.rng.randint(1, 20 * level) * 10
        answer = sp.Rational(percent * amount, 100)
        prompt = self.rng.choice((
            f"Ile wynosi {percent}% z {amount}?",
            f"Oblicz {percent}% liczby {amount}.",
            f"Produkt kosztuje {amount} zł. Ile wynosi {percent}% jego ceny?",
        ))
        return self._exercise(Topic.PERCENT_OF, level, prompt, answer, (f"{percent}% = {percent}/100.", f"{amount} · {percent}/100 = {answer}."))

    def _generate_percent_increase(self, level: int) -> Exercise:
        return self._percent_change(level, increase=True)

    def _generate_percent_decrease(self, level: int) -> Exercise:
        return self._percent_change(level, increase=False)

    def _percent_change(self, level: int, *, increase: bool) -> Exercise:
        amount = self.rng.randint(1, 20 * level) * 10
        percent = self.rng.choice((5, 10, 20, 25, 50))
        multiplier = sp.Rational(100 + percent if increase else 100 - percent, 100)
        answer = amount * multiplier
        verb = "Zwiększ" if increase else "Zmniejsz"
        return self._exercise(Topic.PERCENT_INCREASE if increase else Topic.PERCENT_DECREASE, level, f"{verb} {amount} o {percent}%.", answer, (f"Pomnóż przez {multiplier}: {amount} · {multiplier} = {answer}.",))

    def _generate_percent_original(self, level: int) -> Exercise:
        original = self.rng.randint(1, 20 * level) * 100
        percent = self.rng.choice((10, 20, 25, 40, 50))
        increase = bool(self.rng.randrange(2))
        changed_percent = 100 + percent if increase else 100 - percent
        final = sp.Rational(original * changed_percent, 100)
        answer = sp.Integer(original)
        change_name = "podwyżce" if increase else "obniżce"
        return self._exercise(Topic.PERCENT_ORIGINAL, level, f"Po {change_name} o {percent}% cena wynosi {final}. Jaka była cena przed zmianą?", answer, (f"Po zmianie cena stanowi {changed_percent}% ceny początkowej.", f"Cena początkowa = {final} ÷ {sp.Rational(changed_percent,100)} = {answer}."))

    def _generate_algebra_expression(self, level: int) -> Exercise:
        a, b, c, d = (self._integer(level) for _ in range(4))
        if self.rng.randrange(2):
            expression = (a * X + b) + (c * X + d)
            prompt = f"Uprość wyrażenie: ({a}x + ({b})) + ({c}x + ({d}))."
            steps = (f"Połącz wyrazy podobne: ({a}+{c})x + ({b}+{d}) = {sp.sstr(sp.expand(expression))}.",)
        else:
            expression = (a * X + b) * (c * X + d)
            prompt = f"Rozwiń nawiasy i uprość: ({a}x + ({b}))({c}x + ({d}))."
            steps = (f"Pomnóż każdy składnik przez każdy i zredukuj wyrazy podobne: {sp.sstr(sp.expand(expression))}.",)
        answer = sp.expand(expression)
        return self._exercise(Topic.ALGEBRA_EXPRESSION, level, prompt, answer, steps)

    def _generate_linear_equation(self, level: int) -> Exercise:
        a, c = self.rng.randint(1, 5 * level), self.rng.randint(1, 5 * level)
        while a == c:
            c = self.rng.randint(1, 5 * level)
        root = self._integer(level)
        b, d = self._integer(level), self._integer(level)
        if self.rng.randrange(2):
            left, right = a * X + b, c * X + (a * root + b - c * root)
        else:
            left, right = a * X + b, sp.Integer(a * root + b)
        answer = sp.FiniteSet(root)
        return self._exercise(Topic.LINEAR_EQUATION, level, f"Rozwiąż równanie: {sp.sstr(left)} = {sp.sstr(right)}", answer, (f"Przenieś wyrazy z x na lewą stronę i liczby na prawą.", f"{a-c}x = {(a-c)*root}, więc x = {root}."))

    def _generate_linear_inequality(self, level: int) -> Exercise:
        coefficient = self.rng.choice(tuple(range(-3 * level, 0)) + tuple(range(1, 3 * level + 1)))
        root = self._integer(level)
        intercept = self._integer(level)
        relation, relation_type = self.rng.choice(
            (("<", sp.Lt), ("≤", sp.Le), (">", sp.Gt), ("≥", sp.Ge))
        )
        boundary = coefficient * root + intercept
        solved_relation = relation_type
        if coefficient < 0:
            solved_relation = {
                sp.Lt: sp.Gt,
                sp.Le: sp.Ge,
                sp.Gt: sp.Lt,
                sp.Ge: sp.Le,
            }[relation_type]
        if solved_relation in (sp.Lt, sp.Le):
            answer = sp.Interval(
                -sp.oo, root, right_open=solved_relation is sp.Lt
            )
        else:
            answer = sp.Interval(
                root, sp.oo, left_open=solved_relation is sp.Gt
            )
        direction_note = (
            "Po podzieleniu przez współczynnik ujemny zmieniamy zwrot nierówności."
            if coefficient < 0
            else "Dzielimy obie strony przez dodatni współczynnik."
        )
        return self._exercise(
            Topic.LINEAR_INEQUALITY,
            level,
            f"Rozwiąż nierówność: {coefficient}x + ({intercept}) {relation} {boundary}. "
            "Podaj rozwiązanie jako nierówność z x.",
            answer,
            (
                f"Przenieś wyraz wolny: {coefficient}x {relation} {boundary - intercept}.",
                direction_note,
                f"Granica rozwiązania to x = {root}; zbiór rozwiązań: {sp.sstr(answer)}.",
            ),
        )

    def _generate_linear_system(self, level: int) -> Exercise:
        while True:
            a, b, c, d = (self.rng.randint(-3 * level, 3 * level) or 1 for _ in range(4))
            determinant = a * d - b * c
            if determinant:
                break
        x0, y0 = self._integer(level), self._integer(level)
        first, second = a * x0 + b * y0, c * x0 + d * y0
        answer = sp.Tuple(x0, y0)
        prompt = f"Rozwiąż układ:\n{a}x + ({b})y = {first}\n{c}x + ({d})y = {second}. Podaj (x, y)."
        return self._exercise(Topic.LINEAR_SYSTEM, level, prompt, answer, (f"Wyznacznik macierzy współczynników wynosi {determinant}, więc rozwiązanie jest jedno.", f"Rozwiązanie układu: (x, y) = ({x0}, {y0})."))

    def _generate_quadratic_equation(self, level: int) -> Exercise:
        root1, root2 = self._integer(level), self._integer(level)
        if self.rng.randrange(2):
            polynomial = sp.expand((X - root1) * (X - root2))
            answer = sp.FiniteSet(root1, root2)
            steps = (f"Rozłóż na czynniki: (x − ({root1}))(x − ({root2})) = 0.", f"x = {root1} lub x = {root2}.")
        else:
            polynomial = sp.expand((X - root1) ** 2)
            answer = sp.FiniteSet(root1)
            steps = (f"Zapisz jako kwadrat: (x − ({root1}))² = 0.", f"Jedynym rozwiązaniem jest x = {root1}.")
        return self._exercise(Topic.QUADRATIC_EQUATION, level, f"Rozwiąż równanie kwadratowe: {sp.sstr(polynomial)} = 0.", answer, steps)

    def _generate_area(self, level: int) -> Exercise:
        shape = self.rng.randrange(7)
        if shape == 0:
            a, b = self.rng.randint(1, 10 * level), self.rng.randint(1, 10 * level)
            answer = sp.Integer(a * b)
            return self._exercise(Topic.AREA, level, f"Oblicz pole prostokąta o bokach {a} cm i {b} cm.", answer, (f"P = a · b = {a} · {b} = {answer} cm².",))
        if shape == 1:
            radius = self.rng.randint(1, 4 * level)
            answer = radius**2 * sp.pi
            return self._exercise(Topic.AREA, level, f"Oblicz dokładne pole koła o promieniu {radius} cm. Pozostaw odpowiedź z π.", answer, (f"P = πr² = π·{radius}² = {answer} cm².",))
        if shape == 2:
            side = self.rng.randint(1, 10 * level)
            answer = sp.Integer(side**2)
            return self._exercise(Topic.AREA, level, f"Oblicz pole kwadratu o boku {side} cm.", answer, (f"P = a² = {side}² = {answer} cm².",))
        if shape == 3:
            base, height = self.rng.randint(1, 10 * level), self.rng.randint(1, 10 * level)
            answer = sp.Rational(base * height, 2)
            return self._exercise(Topic.AREA, level, f"Oblicz pole trójkąta o podstawie {base} cm i wysokości {height} cm.", answer, (f"P = a·h/2 = {base}·{height}/2 = {answer} cm².",))
        if shape == 4:
            base, height = self.rng.randint(1, 10 * level), self.rng.randint(1, 10 * level)
            answer = sp.Integer(base * height)
            return self._exercise(Topic.AREA, level, f"Oblicz pole równoległoboku o podstawie {base} cm i wysokości {height} cm.", answer, (f"P = a·h = {base}·{height} = {answer} cm².",))
        if shape == 5:
            diagonal1, diagonal2 = self.rng.randint(1, 10 * level), self.rng.randint(1, 10 * level)
            answer = sp.Rational(diagonal1 * diagonal2, 2)
            return self._exercise(Topic.AREA, level, f"Przekątne rombu mają długości {diagonal1} cm i {diagonal2} cm. Oblicz jego pole.", answer, (f"P = e·f/2 = {diagonal1}·{diagonal2}/2 = {answer} cm².",))
        base1, base2, height = (
            self.rng.randint(1, 10 * level),
            self.rng.randint(1, 10 * level),
            self.rng.randint(1, 10 * level),
        )
        answer = sp.Rational((base1 + base2) * height, 2)
        return self._exercise(Topic.AREA, level, f"Podstawy trapezu mają długości {base1} cm i {base2} cm, a jego wysokość {height} cm. Oblicz pole.", answer, (f"P = (a+b)·h/2 = ({base1}+{base2})·{height}/2 = {answer} cm².",))

    def _generate_perimeter(self, level: int) -> Exercise:
        shape = self.rng.randrange(5)
        if shape == 0:
            a, b = self.rng.randint(1, 10 * level), self.rng.randint(1, 10 * level)
            answer = sp.Integer(2 * (a + b))
            return self._exercise(Topic.PERIMETER, level, f"Oblicz obwód prostokąta o bokach {a} cm i {b} cm.", answer, (f"O = 2(a+b) = 2({a}+{b}) = {answer} cm.",))
        if shape == 1:
            side = self.rng.randint(1, 10 * level)
            answer = sp.Integer(4 * side)
            return self._exercise(Topic.PERIMETER, level, f"Oblicz obwód kwadratu o boku {side} cm.", answer, (f"O = 4a = 4·{side} = {answer} cm.",))
        if shape == 2:
            side1, side2 = self.rng.randint(1, 10 * level), self.rng.randint(1, 10 * level)
            answer = sp.Integer(2 * (side1 + side2))
            return self._exercise(Topic.PERIMETER, level, f"Oblicz obwód równoległoboku o bokach {side1} cm i {side2} cm.", answer, (f"O = 2a+2b = 2·{side1}+2·{side2} = {answer} cm.",))
        if shape == 3:
            side = self.rng.randint(1, 10 * level)
            answer = sp.Integer(4 * side)
            return self._exercise(Topic.PERIMETER, level, f"Oblicz obwód rombu o boku {side} cm.", answer, (f"O = 4a = 4·{side} = {answer} cm.",))
        radius = self.rng.randint(1, 5 * level)
        answer = 2 * sp.pi * radius
        return self._exercise(Topic.PERIMETER, level, f"Podaj dokładny obwód koła o promieniu {radius} cm, używając π.", answer, (f"O = 2πr = 2π·{radius} = {answer} cm.",))

    def _generate_volume(self, level: int) -> Exercise:
        shape = self.rng.randrange(5)
        if shape == 0:
            radius, height = self.rng.randint(1, 5 * level), self.rng.randint(1, 5 * level)
            answer = sp.pi * radius**2 * height
            return self._exercise(Topic.VOLUME, level, f"Oblicz dokładną objętość walca o promieniu {radius} cm i wysokości {height} cm. Pozostaw π.", answer, (f"V = πr²h = π·{radius}²·{height} = {answer} cm³.",))
        if shape == 1:
            radius, height = self.rng.randint(1, 5 * level), self.rng.randint(1, 5 * level)
            answer = sp.pi * radius**2 * height / 3
            return self._exercise(Topic.VOLUME, level, f"Oblicz dokładną objętość stożka o promieniu podstawy {radius} cm i wysokości {height} cm. Pozostaw π.", answer, (f"V = πr²h/3 = π·{radius}²·{height}/3 = {answer} cm³.",))
        if shape == 2:
            radius = self.rng.randint(1, 5 * level)
            answer = sp.Rational(4, 3) * sp.pi * radius**3
            return self._exercise(Topic.VOLUME, level, f"Oblicz dokładną objętość kuli o promieniu {radius} cm. Pozostaw π.", answer, (f"V = 4πr³/3 = 4π·{radius}³/3 = {answer} cm³.",))
        a, b, c = (self.rng.randint(1, 5 * level) for _ in range(3))
        if shape == 3:
            prompt = f"Oblicz objętość prostopadłościanu o wymiarach {a} cm × {b} cm × {c} cm."
        else:
            prompt = f"Pudełko ma wymiary {a} cm, {b} cm i {c} cm. Ile cm³ mieści?"
        answer = sp.Integer(a * b * c)
        return self._exercise(Topic.VOLUME, level, prompt, answer, (f"V = a·b·c = {a}·{b}·{c} = {answer} cm³.",))

    def _generate_surface_area(self, level: int) -> Exercise:
        shape = self.rng.randrange(3)
        if shape == 0:
            side = self.rng.randint(1, 5 * level)
            answer = sp.Integer(6 * side**2)
            return self._exercise(Topic.SURFACE_AREA, level, f"Oblicz pole powierzchni całkowitej sześcianu o krawędzi {side} cm.", answer, (f"P_c = 6a² = 6·{side}² = {answer} cm².",))
        if shape == 1:
            a, b, c = (self.rng.randint(1, 5 * level) for _ in range(3))
            answer = sp.Integer(2 * (a * b + a * c + b * c))
            return self._exercise(Topic.SURFACE_AREA, level, f"Oblicz pole powierzchni prostopadłościanu o wymiarach {a} cm × {b} cm × {c} cm.", answer, (f"P_c = 2(ab+ac+bc) = 2({a}·{b}+{a}·{c}+{b}·{c}) = {answer} cm².",))
        radius, height = self.rng.randint(1, 5 * level), self.rng.randint(1, 5 * level)
        answer = 2 * sp.pi * radius * (radius + height)
        return self._exercise(Topic.SURFACE_AREA, level, f"Oblicz pole powierzchni całkowitej walca o promieniu {radius} cm i wysokości {height} cm. Pozostaw π.", answer, (f"P_c = 2πr² + 2πrh = 2π·{radius}² + 2π·{radius}·{height} = {answer} cm².",))

    def _generate_analytic_geometry(self, level: int) -> Exercise:
        x1, y1, x2, y2 = (self._integer(level) for _ in range(4))
        if self.rng.randrange(2):
            answer = sp.Tuple(sp.Rational(x1 + x2, 2), sp.Rational(y1 + y2, 2))
            prompt = f"Wyznacz środek odcinka o końcach A({x1}, {y1}) i B({x2}, {y2}). Podaj (x, y)."
            steps = (f"Uśrednij współrzędne: (({x1}+{x2})/2, ({y1}+{y2})/2).", f"Środek odcinka to {answer}.")
        else:
            answer = sp.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            prompt = f"Oblicz dokładną długość odcinka o końcach A({x1}, {y1}) i B({x2}, {y2})."
            steps = (f"d = √[({x2}−{x1})² + ({y2}−{y1})²].", f"d = {answer}.")
        return self._exercise(Topic.ANALYTIC_GEOMETRY, level, prompt, answer, steps)

    def _generate_pythagorean(self, level: int) -> Exercise:
        m = self.rng.randint(2, 2 + level)
        n = self.rng.randint(1, m - 1)
        a, b, c = m * m - n * n, 2 * m * n, m * m + n * n
        if self.rng.randrange(2):
            answer = sp.Integer(c)
            prompt = f"Trójkąt prostokątny ma przyprostokątne {a} i {b}. Oblicz długość przeciwprostokątnej."
            steps = (f"c² = {a}² + {b}² = {a*a+b*b}.", f"c = √{a*a+b*b} = {answer}.")
        else:
            legs = (a, b)
            known_leg = self.rng.choice(legs)
            missing_leg = b if known_leg == a else a
            answer = sp.Integer(missing_leg)
            prompt = f"Trójkąt prostokątny ma przeciwprostokątną {c} i jedną przyprostokątną {known_leg}. Oblicz drugą przyprostokątną."
            steps = (f"Druga przyprostokątna² = {c}² − {known_leg}².", f"√({c*c} − {known_leg*known_leg}) = {answer}.")
        return self._exercise(Topic.PYTHAGOREAN, level, prompt, answer, steps)

    def _generate_powers(self, level: int) -> Exercise:
        base = self.rng.randint(2, 5 + level)
        exponent = self.rng.randint(2, level + 2)
        if level >= 3 and self.rng.randrange(2):
            exponent = -exponent
        answer = sp.Integer(base**exponent) if exponent >= 0 else sp.Rational(1, base ** -exponent)
        return self._exercise(Topic.POWERS, level, f"Oblicz: {base}^{exponent}.", answer, (f"{base}^{exponent} = {answer}.",))

    def _generate_square_roots(self, level: int) -> Exercise:
        value = self.rng.randint(2, 12 * level)
        radicand = value * value if level == 1 else value * value * self.rng.choice((2, 3, 5))
        coefficient = self.rng.randint(1, level)
        answer = coefficient * sp.sqrt(radicand)
        prompt = f"Uprość wyrażenie: {coefficient}√{radicand}."
        return self._exercise(Topic.SQUARE_ROOTS, level, prompt, answer, (f"Wyłącz czynnik będący kwadratem spod pierwiastka: {coefficient}√{radicand} = {answer}.",))

    def _generate_function_value(self, level: int) -> Exercise:
        a, b, c, point = (self._integer(level) for _ in range(4))
        if self.rng.randrange(2):
            expression = a * X + c
        else:
            expression = a * X**2 + b * X + c
        answer = sp.expand(expression.subs(X, point))
        return self._exercise(Topic.FUNCTION_VALUE, level, f"Dla f(x) = {sp.sstr(expression)} oblicz f({point}).", answer, (f"Podstaw x = {point}: f({point}) = {a}·{point}² + {b}·{point} + {c} = {answer}.",))

    def _generate_graph_point(self, level: int) -> Exercise:
        slope, intercept, point = self._integer(level), self._integer(level), self._integer(level)
        if self.rng.randrange(2):
            expression = slope * X**2 + intercept
        else:
            expression = slope * X + intercept
        answer = sp.Tuple(point, expression.subs(X, point))
        return self._exercise(Topic.GRAPH_POINT, level, f"Punkt wykresu y = {sp.sstr(expression)} ma współrzędną x = {point}. Podaj punkt (x, y).", answer, (f"Oblicz y = {slope}·{point} + ({intercept}) = {answer[1]}.",))

    def _generate_sequences(self, level: int) -> Exercise:
        first = self._integer(level)
        index = self.rng.randint(4, 8 + level)
        if self.rng.randrange(2):
            difference = self.rng.choice(tuple(range(-level, 0)) + tuple(range(1, level + 1)))
            answer = sp.Integer(first + (index - 1) * difference)
            prompt = f"Ciąg arytmetyczny ma a₁ = {first} i różnicę r = {difference}. Oblicz a_{index}."
            steps = (f"a_n = a₁ + (n−1)r.", f"a_{index} = {first} + ({index}−1)·({difference}) = {answer}.")
        else:
            ratio = self.rng.choice(tuple(range(-3, 0)) + tuple(range(2, 4)))
            answer = sp.Integer(first * ratio ** (index - 1))
            prompt = f"Ciąg geometryczny ma a₁ = {first} i iloraz q = {ratio}. Oblicz a_{index}."
            steps = (f"a_n = a₁·q^(n−1).", f"a_{index} = {first}·({ratio})^({index}−1) = {answer}.")
        return self._exercise(Topic.SEQUENCES, level, prompt, answer, steps)

    def _generate_trigonometry(self, level: int) -> Exercise:
        angle, sine, cosine, tangent = self.rng.choice(_TRIG_VALUES[:-1])
        function, answer = self.rng.choice(
            (("sin", sine), ("cos", cosine), ("tan", tangent))
        )
        return self._exercise(Topic.TRIGONOMETRY, level, f"Oblicz dokładną wartość {function}({angle}°).", answer, (f"Korzystając z wartości szczególnych: {function}({angle}°) = {sp.sstr(answer)}.",))

    def _generate_logarithms(self, level: int) -> Exercise:
        base = self.rng.randint(2, 5 + level)
        exponent = self.rng.randint(1, 3 + level)
        argument = base**exponent
        answer = sp.Integer(exponent)
        if self.rng.randrange(2):
            prompt, result = f"Oblicz: log_{base}({argument}).", answer
            steps = (f"log_{base}({argument}) = x oznacza {base}^x = {argument}.", f"Ponieważ {base}^{exponent} = {argument}, wynik to {exponent}.")
        else:
            prompt, result = f"Rozwiąż równanie log_{base}(x) = {exponent}.", sp.Integer(argument)
            steps = (f"Zapisz w postaci wykładniczej: x = {base}^{exponent}.", f"x = {argument}.")
        return self._exercise(Topic.LOGARITHMS, level, prompt, result, steps)

    def _generate_combinatorics(self, level: int) -> Exercise:
        if self.rng.randrange(2):
            available = self.rng.randint(4, 5 + 2 * level)
            selected = self.rng.randint(2, min(available - 1, 3 + level))
            answer = sp.binomial(available, selected)
            prompt = f"Z {available} osób wybieramy {selected} do zespołu. Ile różnych zespołów można utworzyć?"
            steps = (f"Kolejność wyboru nie ma znaczenia, więc używamy symbolu Newtona.", f"C({available}, {selected}) = {answer}.")
        else:
            choices = [self.rng.randint(2, 3 + level) for _ in range(3)]
            answer = sp.Integer(math.prod(choices))
            prompt = f"Można wybrać po jednej opcji z trzech kategorii: {choices[0]}, {choices[1]} i {choices[2]} możliwości. Ile jest zestawów?"
            steps = (f"Stosujemy regułę mnożenia: {choices[0]}·{choices[1]}·{choices[2]} = {answer}.",)
        return self._exercise(Topic.COMBINATORICS, level, prompt, answer, steps)

    def _generate_probability(self, level: int) -> Exercise:
        total = self.rng.randint(4, 6 + 4 * level)
        favorable = self.rng.randint(1, total - 1)
        answer = sp.Rational(favorable, total)
        colors = self.rng.choice(("czerwone", "niebieskie", "zielone", "oznaczone"))
        prompt = f"W doświadczeniu wszystkie {total} wyników są jednakowo prawdopodobne, a {favorable} z nich są sprzyjające. Oblicz prawdopodobieństwo zdarzenia."
        if colors == "oznaczone":
            prompt = f"W pudełku jest {total} jednakowo prawdopodobnych losów, w tym {favorable} wygrywających. Oblicz prawdopodobieństwo wygranej."
        steps = (f"P(A) = liczba wyników sprzyjających / liczba wszystkich wyników = {favorable}/{total}.", f"P(A) = {answer}.")
        return self._exercise(Topic.PROBABILITY, level, prompt, answer, steps)

    def _generate_statistics(self, level: int) -> Exercise:
        values = [self.rng.randint(-2 * level, 5 * level) for _ in range(5)]
        if self.rng.randrange(2):
            answer = sp.Rational(sum(values), len(values))
            measure = "średnią arytmetyczną"
            steps = (f"Dodaj dane i podziel przez ich liczbę: ({' + '.join(map(str, values))}) / {len(values)}.", f"Średnia wynosi {answer}.")
        else:
            ordered = sorted(values)
            answer = sp.Integer(ordered[len(ordered) // 2])
            measure = "medianę"
            steps = (f"Uporządkuj dane rosnąco: {', '.join(map(str, ordered))}.", f"Środkowa wartość to {answer}.")
        prompt = f"Wyznacz {measure} zestawu danych: {', '.join(map(str, values))}."
        return self._exercise(Topic.STATISTICS, level, prompt, answer, steps)

    def _generate_limits(self, level: int) -> Exercise:
        point = self._integer(level, positive=True)
        if self.rng.randrange(2):
            a, b = self._integer(level), self._integer(level)
            expression = a * X**2 + b * X + 1
            answer = sp.limit(expression, X, point)
            prompt = f"Oblicz granicę lim (x→{point}) [{sp.sstr(expression)}]."
            steps = (f"Wielomian jest ciągły, więc podstawiamy x = {point}.", f"Granica wynosi {answer}.")
        else:
            expression = (X**2 - point**2) / (X - point)
            answer = sp.limit(expression, X, point)
            prompt = f"Oblicz granicę lim (x→{point}) [(x² − {point**2})/(x − {point})]."
            steps = (f"Rozłóż licznik: x² − {point**2} = (x−{point})(x+{point}).", f"Po skróceniu granica wynosi {answer}.")
        return self._exercise(Topic.LIMITS, level, prompt, answer, steps)

    def _generate_derivatives(self, level: int) -> Exercise:
        a, b, c = (self._integer(level) for _ in range(3))
        if self.rng.randrange(3) == 0:
            expression = a * sp.sin(X)
        elif self.rng.randrange(2):
            expression = a * X**2 + b * X
        else:
            expression = a * X**3 + b * X**2 + c * X
        answer = sp.diff(expression, X)
        return self._exercise(Topic.DERIVATIVES, level, f"Wyznacz pochodną funkcji f(x) = {sp.sstr(expression)}.", answer, (f"Zastosuj regułę potęgową do każdego składnika: f′(x) = {sp.sstr(answer)}.",))

    def _generate_integrals(self, level: int) -> Exercise:
        a, b, c = (self._integer(level) for _ in range(3))
        if self.rng.randrange(3) == 0:
            expression = a * sp.cos(X)
        elif self.rng.randrange(2):
            expression = a * X + c
        else:
            expression = a * X**2 + b * X + c
        answer = sp.integrate(expression, X)
        return self._exercise(Topic.INTEGRALS, level, f"Oblicz całkę nieoznaczoną ∫({sp.sstr(expression)}) dx. Stałą całkowania pomiń.", answer, (f"Całkuj składnik po składniku: ∫xⁿ dx = xⁿ⁺¹/(n+1).", f"F(x) = {sp.sstr(answer)} + C."), answer_mode="antiderivative")


def generate_exercise(
    topic: Topic | str,
    difficulty: int = 1,
    *,
    rng: random.Random | None = None,
) -> Exercise:
    return ExerciseGenerator(rng).generate(topic, difficulty)
