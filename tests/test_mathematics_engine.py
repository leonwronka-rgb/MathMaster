from __future__ import annotations

import random
import unittest

import sympy as sp

from mathematics.engine import MathEngine
from mathematics.solutions import Exercise
from mathematics.topics import Topic
from mathematics.validators import AnswerParseError, is_correct_answer, parse_answer


class MathEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = MathEngine(random.Random(4))

    def test_answers_accept_equivalent_fractions_decimals_and_expressions(self) -> None:
        fraction = self.engine.generate(Topic.FRACTION_ADDITION, 2)
        self.assertTrue(is_correct_answer(fraction, fraction.answer_text))
        decimal_task = Exercise(Topic.PERCENT_OF, 1, "test", sp.Rational(1, 2), "")
        self.assertTrue(is_correct_answer(decimal_task, "0.5"))
        expression_task = Exercise(
            Topic.ALGEBRA_EXPRESSION, 1, "test", sp.Symbol("x") + 1, ""
        )
        self.assertTrue(is_correct_answer(expression_task, "1+x"))
        self.assertFalse(is_correct_answer(expression_task, "1-x"))

    def test_power_answer_must_evaluate_instead_of_repeat_the_question(self) -> None:
        exercise = Exercise(Topic.POWERS, 1, "Oblicz: 6^4.", sp.Integer(1296), "")

        self.assertFalse(is_correct_answer(exercise, "6^4"))
        self.assertFalse(is_correct_answer(exercise, "6 ** 4"))
        self.assertTrue(is_correct_answer(exercise, "1296"))

    def test_tuple_and_set_answers_are_compared_mathematically(self) -> None:
        system = self.engine.generate(Topic.LINEAR_SYSTEM, 2)
        self.assertTrue(is_correct_answer(system, system.answer_text))
        roots = self.engine.generate(Topic.QUADRATIC_EQUATION, 2)
        self.assertTrue(is_correct_answer(roots, roots.answer_text))
        self.assertTrue(is_correct_answer(roots, str(tuple(roots.answer))))
        linear = self.engine.generate(Topic.LINEAR_EQUATION, 2)
        self.assertTrue(is_correct_answer(linear, str(next(iter(linear.answer)))))

    def test_indefinite_integrals_ignore_additive_constant(self) -> None:
        integral = self.engine.generate(Topic.INTEGRALS, 2)
        self.assertTrue(is_correct_answer(integral, f"({integral.answer_text}) + 42"))

    def test_expression_parser_does_not_evaluate_python_code(self) -> None:
        for invalid in (
            "__import__('os')", "open('secret')", "1/0", "x.__class__",
            "x**1000", "2**101",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(AnswerParseError):
                    parse_answer(invalid)

    def test_symbolic_operations_and_function_samples(self) -> None:
        self.assertEqual(self.engine.simplify("x+x"), 2 * sp.Symbol("x"))
        self.assertEqual(self.engine.solve_equation("x^2-1"), sp.FiniteSet(-1, 1))
        self.assertEqual(
            self.engine.solve_system(("x+y-3", "x-y-1")), (2, 1)
        )
        self.assertEqual(self.engine.derivative("x^3"), 3 * sp.Symbol("x") ** 2)
        self.assertEqual(self.engine.integral("2*x"), sp.Symbol("x") ** 2)
        self.assertEqual(self.engine.limit("x^2", "3"), 9)
        points = self.engine.function_samples("x^2", -1, 1, samples=3)
        self.assertEqual(points, ((-1.0, 1.0), (0.0, 0.0), (1.0, 1.0)))

    def test_mathematical_symbols_and_function_names_are_case_insensitive(self) -> None:
        expected = sp.Symbol("x") + sp.pi
        for answer in ("X+PI", "x+Pi", "x+pI", "x+π"):
            with self.subTest(answer=answer):
                self.assertEqual(parse_answer(answer), expected)
        task = Exercise(Topic.ALGEBRA_EXPRESSION, 1, "test", sp.Symbol("x") + sp.pi, "")
        self.assertTrue(is_correct_answer(task, "X + PI"))
        self.assertEqual(parse_answer("SIN(PI/2)"), sp.Integer(1))

    def test_linear_inequality_answers_accept_equivalent_comparisons(self) -> None:
        generator = MathEngine(random.Random(97))
        for _ in range(20):
            exercise = generator.generate(Topic.LINEAR_INEQUALITY, 3)
            self.assertTrue(
                is_correct_answer(exercise, exercise.answer_text),
                exercise.answer_text,
            )
        self.assertEqual(parse_answer("x < 3"), sp.Interval(-sp.oo, 3, right_open=True))
        self.assertEqual(parse_answer("3 <= x"), sp.Interval(3, sp.oo, left_open=False))
        self.assertTrue(
            is_correct_answer(
                Exercise(
                    Topic.LINEAR_INEQUALITY,
                    1,
                    "test",
                    sp.Interval(-sp.oo, 3, right_open=True),
                    "",
                ),
                "x < 3",
            )
        )

    def test_plot_range_and_sample_count_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.function_samples("x", 1, 1)
        with self.assertRaises(ValueError):
            self.engine.function_samples("x", 0, 1, samples=1)


if __name__ == "__main__":
    unittest.main()
