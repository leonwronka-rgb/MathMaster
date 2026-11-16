from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppSetting:
    key: str
    value: str


@dataclass(frozen=True, slots=True)
class ExamAnswerRecord:
    question_number: int
    topic: str
    question: str
    submitted_answer: str
    correct_answer: str
    solution: str
    correct: bool
    marked_for_review: bool