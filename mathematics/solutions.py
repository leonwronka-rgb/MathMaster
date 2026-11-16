from __future__ import annotations

from dataclasses import dataclass

import sympy as sp

from mathematics.topics import Topic


@dataclass(frozen=True, slots=True)
class Exercise:
    topic: Topic
    difficulty: int
    prompt: str
    answer: sp.Basic
    solution: str
    answer_mode: str = "equivalent"
    bank_task_id: str | None = None
    generator_id: str | None = None
    generator_parameters_json: str = "{}"

    @property
    def answer_text(self) -> str:
        return format_answer(self.answer, self.topic)


def describe_solution(
    steps: tuple[str, ...], answer: sp.Basic, topic: Topic | None = None
) -> str:
    return "\n".join((*steps, f"Odpowiedź: {format_answer(answer, topic)}"))


def format_answer(answer: sp.Basic, topic: Topic | None = None) -> str:
    if topic == Topic.LINEAR_INEQUALITY and isinstance(answer, sp.Interval):
        if answer.start == -sp.oo:
            relation = "<" if answer.right_open else "≤"
            return f"x {relation} {sp.sstr(answer.end)}"
        if answer.end == sp.oo:
            relation = ">" if answer.left_open else "≥"
            return f"x {relation} {sp.sstr(answer.start)}"
    return sp.sstr(answer)
