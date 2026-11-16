from __future__ import annotations

from collections.abc import Callable
import io
import math
import struct
import sys
import tkinter as tk
from time import monotonic
from typing import Any
import wave

import customtkinter as ctk

from learning.learning_service import (
    LearningError,
    LearningService,
    LearningSession,
    LearningStorageError,
    SessionSummary,
)
from mathematics.topics import (
    DIFFICULTY_LEVELS,
    DIFFICULTY_NAMES,
    TOPIC_CATEGORIES,
    TOPIC_REQUIREMENTS,
    Topic,
)
from ui.theme import COLORS

_TOPIC_LABELS = {
    Topic.ADDITION: "Dodawanie",
    Topic.SUBTRACTION: "Odejmowanie",
    Topic.MULTIPLICATION: "Mnożenie",
    Topic.DIVISION: "Dzielenie",
    Topic.ORDER_OF_OPERATIONS: "Kolejność działań",
    Topic.FRACTION_SIMPLIFY: "Skracanie ułamków",
    Topic.FRACTION_EXPAND: "Rozszerzanie ułamków",
    Topic.FRACTION_ADDITION: "Dodawanie ułamków",
    Topic.FRACTION_SUBTRACTION: "Odejmowanie ułamków",
    Topic.FRACTION_MULTIPLICATION: "Mnożenie ułamków",
    Topic.FRACTION_DIVISION: "Dzielenie ułamków",
    Topic.PERCENT_OF: "Procent z liczby",
    Topic.PERCENT_INCREASE: "Podwyżki procentowe",
    Topic.PERCENT_DECREASE: "Obniżki procentowe",
    Topic.PERCENT_ORIGINAL: "Wartość początkowa",
    Topic.ALGEBRA_EXPRESSION: "Wyrażenia algebraiczne",
    Topic.LINEAR_EQUATION: "Równania liniowe",
    Topic.LINEAR_INEQUALITY: "Nierówności liniowe",
    Topic.LINEAR_SYSTEM: "Układy równań",
    Topic.QUADRATIC_EQUATION: "Równania kwadratowe",
    Topic.AREA: "Pola figur",
    Topic.PERIMETER: "Obwody figur",
    Topic.VOLUME: "Objętość brył",
    Topic.SURFACE_AREA: "Pole powierzchni brył",
    Topic.PYTHAGOREAN: "Twierdzenie Pitagorasa",
    Topic.ANALYTIC_GEOMETRY: "Geometria analityczna",
    Topic.POWERS: "Potęgi",
    Topic.SQUARE_ROOTS: "Pierwiastki",
    Topic.FUNCTION_VALUE: "Wartość funkcji",
    Topic.GRAPH_POINT: "Punkty na wykresie",
    Topic.SEQUENCES: "Ciągi",
    Topic.TRIGONOMETRY: "Trygonometria",
    Topic.LOGARITHMS: "Logarytmy",
    Topic.COMBINATORICS: "Kombinatoryka",
    Topic.PROBABILITY: "Prawdopodobieństwo",
    Topic.STATISTICS: "Statystyka",
    Topic.LIMITS: "Granice",
    Topic.DERIVATIVES: "Pochodne",
    Topic.INTEGRALS: "Całki",
}


class LearningScreen(ctk.CTkScrollableFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        user_id: int,
        learning_service: LearningService,
        on_gamification_update: Callable[[], None] | None = None,
        initial_topic: Topic | None = None,
        catalog_topic_id: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            parent,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.user_id = user_id
        self.learning_service = learning_service
        self.on_gamification_update = on_gamification_update
        self.catalog_topic_id = catalog_topic_id
        self.preferences = preferences or {}
        self.session: LearningSession | None = None
        self.last_summary: SessionSummary | None = None
        self._session_deadline: float | None = None
        self._timer_after_id: str | None = None
        self._auto_next_after_id: str | None = None
        self._progress_text = ""
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Nauka matematyki",
            anchor="w",
            font=ctk.CTkFont(size=27, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", pady=(4, 5))
        ctk.CTkLabel(
            self,
            text="Wybierz temat, ustaw poziom i ćwicz we własnym tempie.",
            anchor="w",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
        ).grid(row=1, column=0, sticky="ew", pady=(0, 17))

        self.setup_panel = ctk.CTkFrame(
            self, fg_color=COLORS["card"], corner_radius=18,
            border_color=COLORS["border"], border_width=1,
        )
        self.setup_panel.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        self.setup_panel.grid_columnconfigure((0, 1), weight=1, uniform="setup")
        self.category_values = tuple(TOPIC_CATEGORIES)
        self.category = ctk.CTkOptionMenu(
            self.setup_panel,
            values=list(self.category_values),
            command=self._category_changed,
            fg_color=COLORS["surface"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        self._field_label(self.setup_panel, "Kategoria", 0, 0)
        self.category.grid(row=1, column=0, sticky="ew", padx=(18, 8), pady=(0, 13))
        self.topic_values: tuple[Topic, ...] = ()
        self.topic = ctk.CTkOptionMenu(
            self.setup_panel,
            values=[],
            command=self._topic_changed,
            fg_color=COLORS["surface"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        self._field_label(self.setup_panel, "Temat", 0, 1)
        self.topic.grid(row=1, column=1, sticky="ew", padx=(8, 18), pady=(0, 13))
        self.requirements_label = ctk.CTkLabel(
            self.setup_panel,
            text="",
            anchor="w",
            justify="left",
            wraplength=800,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11),
        )
        self.requirements_label.grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 4)
        )
        category_default = self.preferences.get("default_category", self.category_values[0])
        if category_default not in self.category_values:
            category_default = self.category_values[0]
        self.category.set(category_default)
        self._category_changed(category_default)
        if initial_topic is not None:
            category = next(
                name
                for name, topics in TOPIC_CATEGORIES.items()
                if initial_topic in topics
            )
            self.category.set(category)
            self._category_changed(category)
            self.topic.set(_TOPIC_LABELS[initial_topic])
            self._topic_changed(_TOPIC_LABELS[initial_topic])

        self.level_values = tuple(DIFFICULTY_NAMES[value] for value in DIFFICULTY_LEVELS)
        self.difficulty = ctk.CTkOptionMenu(
            self.setup_panel, values=list(self.level_values),
            fg_color=COLORS["surface"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        self.difficulty.set(
            DIFFICULTY_NAMES.get(self.preferences.get("default_difficulty", 1), DIFFICULTY_NAMES[1])
        )
        self._field_label(self.setup_panel, "Poziom trudności", 3, 0)
        self.difficulty.grid(row=4, column=0, sticky="ew", padx=(18, 8), pady=(0, 18))
        self.count_values = ("5", "10", "15", "20", "30", "50", "100")
        self.question_count = ctk.CTkOptionMenu(
            self.setup_panel, values=list(self.count_values),
            fg_color=COLORS["surface"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        initial_count = str(self.preferences.get("questions_per_session", 10))
        self.question_count.set(
            initial_count if initial_count in self.count_values else "10"
        )
        self._field_label(self.setup_panel, "Liczba zadań", 3, 1)
        self.question_count.grid(row=4, column=1, sticky="ew", padx=(8, 18), pady=(0, 18))
        self.start_button = ctk.CTkButton(
            self.setup_panel, text="Rozpocznij ćwiczenia", height=42,
            corner_radius=12, fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_session,
        )
        self.start_button.grid(row=5, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 18))

        self.status = ctk.CTkLabel(
            self, text="", anchor="w", wraplength=650,
            font=ctk.CTkFont(size=12), text_color="#FCA5A5",
        )
        self.status.grid(row=3, column=0, sticky="ew", pady=(0, 8))

        self.session_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.session_panel.grid_columnconfigure(0, weight=1)
        self._build_session_panel()
        self.summary_panel = ctk.CTkFrame(
            self, fg_color="transparent"
        )
        self.summary_panel.grid_columnconfigure(0, weight=1)

        self.history_panel = ctk.CTkFrame(
            self, fg_color=COLORS["card"], corner_radius=18,
            border_color=COLORS["border"], border_width=1,
        )
        self.history_panel.grid(row=4, column=0, sticky="ew", pady=(8, 22))
        self._show_history()

    @staticmethod
    def _field_label(
        parent: ctk.CTkFrame, text: str, row: int, column: int
    ) -> None:
        ctk.CTkLabel(
            parent, text=text, anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["muted"],
        ).grid(
            row=row, column=column, sticky="ew",
            padx=(18, 8) if column == 0 else (8, 18), pady=(14, 5),
        )

    def _category_changed(self, category: str) -> None:
        topics = TOPIC_CATEGORIES[category]
        self.topic_values = topics
        labels = [_TOPIC_LABELS[topic] for topic in topics]
        self.topic.configure(values=labels)
        self.topic.set(labels[0])
        self._update_topic_requirements(topics[0])

    def _topic_changed(self, label: str) -> None:
        topic = next((topic for topic in self.topic_values if _TOPIC_LABELS[topic] == label), None)
        if topic is None:
            return
        category = next(
            name for name, topics in TOPIC_CATEGORIES.items() if topic in topics
        )
        self.category.set(category)
        self.topic_values = TOPIC_CATEGORIES[category]
        self._update_topic_requirements(topic)

    def _update_topic_requirements(self, topic: Topic) -> None:
        requirements = TOPIC_REQUIREMENTS[topic]
        text = "Wymagania dla tematu:\n" + "\n".join(
            f"• {requirement}" for requirement in requirements
        )
        self.requirements_label.configure(text=text)

    def _build_session_panel(self) -> None:
        self.progress_label = ctk.CTkLabel(
            self.session_panel, text="", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=COLORS["muted"],
        )
        self.progress_label.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        self.progress_bar = ctk.CTkProgressBar(
            self.session_panel, height=9, corner_radius=8,
            fg_color=COLORS["border"], progress_color=COLORS["accent"],
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self.progress_bar.set(0)

        self.question_card = ctk.CTkFrame(
            self.session_panel, fg_color=COLORS["card"], corner_radius=18,
            border_color=COLORS["border"], border_width=1,
        )
        self.question_card.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.question_card.grid_columnconfigure(0, weight=1)
        self.question_text = ctk.CTkLabel(
            self.question_card, text="", anchor="w", justify="left",
            wraplength=700, font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text"],
        )
        self.question_text.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        self.answer_entry = ctk.CTkEntry(
            self.question_card, height=43, corner_radius=11,
            placeholder_text="Wpisz odpowiedź (np. 3/4, 0.75, x+2 lub (1, 2))",
            fg_color=COLORS["background"], border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.answer_entry.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        self.feedback = ctk.CTkLabel(
            self.question_card, text="", anchor="w", justify="left",
            wraplength=700, font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.feedback.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 4))
        self.solution_label = ctk.CTkLabel(
            self.question_card, text="", anchor="w", justify="left",
            wraplength=700, font=ctk.CTkFont(size=12), text_color=COLORS["muted"],
        )
        self.hint_button = ctk.CTkButton(
            self.question_card, text="Pokaż podpowiedź", height=30,
            command=self._show_hint, fg_color=COLORS["surface"],
            hover_color=COLORS["card_hover"],
        )
        self.hint_button.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 7))
        self.hint_label = ctk.CTkLabel(
            self.question_card, text="", anchor="w", justify="left",
            wraplength=700, text_color=COLORS["blue"],
        )
        self.hint_label.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 5))
        self.feedback.grid_configure(row=4)
        self.solution_label.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 16))

        self.adaptation_panel = ctk.CTkFrame(
            self.session_panel, fg_color=COLORS["accent_soft"], corner_radius=14
        )
        self.adaptation_label = ctk.CTkLabel(
            self.adaptation_panel, text="", wraplength=600,
            font=ctk.CTkFont(size=12), text_color=COLORS["text"],
        )
        self.adaptation_label.pack(padx=14, pady=(12, 8))
        buttons = ctk.CTkFrame(self.adaptation_panel, fg_color="transparent")
        buttons.pack(pady=(0, 12))
        self.adapt_yes = ctk.CTkButton(
            buttons, text="Zmień poziom", height=34, corner_radius=10,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=lambda: self._resolve_adaptation(True),
        )
        self.adapt_yes.pack(side="left", padx=5)
        self.adapt_no = ctk.CTkButton(
            buttons, text="Pozostań na obecnym", height=34, corner_radius=10,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
            command=lambda: self._resolve_adaptation(False),
        )
        self.adapt_no.pack(side="left", padx=5)

        actions = ctk.CTkFrame(self.session_panel, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        self.check_button = ctk.CTkButton(
            actions, text="Sprawdź odpowiedź", height=40, corner_radius=11,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self._check_answer,
        )
        self.check_button.pack(side="left")
        self.next_button = ctk.CTkButton(
            actions, text="Następne zadanie  →", height=40, corner_radius=11,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
            command=self._next_question,
        )
        self.quit_button = ctk.CTkButton(
            actions, text="Przerwij sesję", height=40, corner_radius=11,
            fg_color="transparent", hover_color=COLORS["card_hover"],
            text_color=COLORS["muted"], command=self._abort_session,
        )
        self.quit_button.pack(side="right")

    def _start_session(self) -> None:
        self.status.configure(text="")
        try:
            topic_label = self.topic.get()
            topic = next(
                topic for topic in self.topic_values
                if _TOPIC_LABELS[topic] == topic_label
            )
            self.session = self.learning_service.start_session(
                self.user_id,
                topic,
                next(
                    level
                    for level, label in DIFFICULTY_NAMES.items()
                    if label == self.difficulty.get()
                ),
                int(self.question_count.get()),
                self.catalog_topic_id,
            )
            duration = int(self.preferences.get("session_duration_minutes", 25))
            self._session_deadline = monotonic() + duration * 60
            self.last_summary = None
            self._show_session()
            self._show_question()
            self._schedule_session_timer()
        except (ValueError, LearningError) as error:
            self.status.configure(text=str(error))

    def _show_session(self) -> None:
        self.setup_panel.grid_remove()
        self.history_panel.grid_remove()
        self.session_panel.grid(row=2, column=0, sticky="ew", pady=(0, 22))

    def _show_question(self) -> None:
        if self.session is None:
            return
        self.adaptation_panel.grid_forget()
        self.feedback.configure(text="")
        self.solution_label.configure(text="")
        self.hint_label.configure(text="")
        self.hint_button.grid() if self.preferences.get("show_hints", True) else self.hint_button.grid_remove()
        self.answer_entry.configure(state="normal")
        self.answer_entry.delete(0, "end")
        self.check_button.configure(state="normal")
        self.check_button.pack(side="left")
        self.next_button.pack_forget()
        self.question_text.configure(
            text=(
                f"Zadanie {self.session.answered_count + 1} z "
                f"{self.session.total_questions}  ·  {DIFFICULTY_NAMES[self.session.difficulty]}\n\n"
                f"{self.session.current_exercise.prompt}"
            )
        )
        self._update_progress()
        self.answer_entry.focus_set()

    def _check_answer(self) -> None:
        if self.session is None:
            return
        try:
            result = self.session.answer(self.answer_entry.get())
        except (ValueError, LearningStorageError) as error:
            self.feedback.configure(text=str(error), text_color="#FCA5A5")
            return
        self._play_feedback_sound(result.correct)

        if result.correct:
            message, color = "✓  Poprawna odpowiedź!", COLORS["success"]
        else:
            message = f"✗  Niepoprawna odpowiedź. Poprawny wynik: {result.correct_answer}"
            color = "#FCA5A5"
        details = [
            f"{message}     •     Poprawne: {result.correct_count}"
            f"     Błędy: {result.incorrect_count}",
            f"+{result.xp_awarded} XP  ·  Łącznie: {result.total_xp} XP",
        ]
        if result.leveled_up:
            details.append(f"🎉 Awans na poziom {result.level}!")
        details.extend(
            f"🏅 Osiągnięcie: {achievement.title} (+{achievement.xp_reward} XP)"
            for achievement in result.achievements
        )
        self.feedback.configure(text="\n".join(details), text_color=color)
        if self.on_gamification_update is not None:
            self.on_gamification_update()
        if result.correct or self.preferences.get("show_solution_after_error", True):
            self.solution_label.configure(text=f"Rozwiązanie:\n{result.solution}")
        else:
            self.solution_label.configure(text="Rozwiązanie jest ukryte. Możesz je włączyć w ustawieniach.")
        self.answer_entry.configure(state="disabled")
        self.check_button.configure(state="disabled")
        self._update_progress()

        if (
            result.suggested_difficulty is not None
            and not result.session_finished
            and self.preferences.get("adaptive_difficulty", True)
        ):
            direction = "łatwiejsze" if result.suggested_difficulty < self.session.difficulty else "trudniejsze"
            self.adaptation_label.configure(
                text=(
                    f"Masz za sobą 3 odpowiedzi z rzędu w tym samym wyniku. "
                    f"Czy chcesz zmienić poziom {direction} na "
                    f"{DIFFICULTY_NAMES[result.suggested_difficulty]}? Poziom zmieni się dopiero po Twojej zgodzie."
                )
            )
            self.adaptation_panel.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        else:
            if result.suggested_difficulty is not None and not result.session_finished:
                try:
                    self.session.resolve_difficulty_change(False)
                except LearningError as error:
                    self.status.configure(text=str(error))
            self._show_next_button(result.session_finished)
            if self.preferences.get("auto_next_question") and not result.session_finished:
                self._auto_next_after_id = self.after(800, self._next_question)

    def _resolve_adaptation(self, accept: bool) -> None:
        if self.session is None:
            return
        try:
            level = self.session.resolve_difficulty_change(accept)
            self.adaptation_panel.grid_forget()
            if accept:
                self.feedback.configure(
                    text=f"{self.feedback.cget('text')}     •     Ustawiono poziom {level}.",
                )
            else:
                self.feedback.configure(
                    text=f"{self.feedback.cget('text')}     •     Pozostajesz na poziomie {level}.",
                )
            self._show_next_button(self.session.finished)
        except LearningError as error:
            self.status.configure(text=str(error))

    def _show_next_button(self, session_finished: bool) -> None:
        self.next_button.configure(
            text="Zobacz podsumowanie" if session_finished else "Następne zadanie  →",
            command=self._show_summary if session_finished else self._next_question,
        )
        self.next_button.pack(side="left", padx=(9, 0))

    def _show_hint(self) -> None:
        if not self.preferences.get("show_hints", True) or self.session is None:
            return
        steps = self.session.current_exercise.solution.splitlines()
        hint = next((step for step in steps if step.strip()), "Spróbuj zastosować poznane wzory.")
        if hint.startswith("Odpowiedź:"):
            self.hint_label.configure(text="Wskazówka: rozpisz działanie na mniejsze kroki.")
        else:
            self.hint_label.configure(text=f"Wskazówka: {hint}")

    def _schedule_session_timer(self) -> None:
        self._timer_after_id = self.after(1000, self._update_session_timer)

    def _update_session_timer(self) -> None:
        if self.session is None or self._session_deadline is None:
            return
        remaining = max(0, int(self._session_deadline - monotonic()))
        minutes, seconds = divmod(remaining, 60)
        self.progress_label.configure(
            text=f"{self._progress_text}     ·     Czas: {minutes:02d}:{seconds:02d}"
        )
        if remaining == 0:
            self.session.finish(aborted=False)
            self.status.configure(text="Czas sesji minął.")
            self._show_summary()
            return
        self._schedule_session_timer()

    def _next_question(self) -> None:
        if self._auto_next_after_id is not None:
            try:
                self.after_cancel(self._auto_next_after_id)
            except tk.TclError:
                pass
            self._auto_next_after_id = None
        if self.session is None:
            return
        try:
            self.session.next_question()
            self._show_question()
        except LearningError as error:
            self.status.configure(text=str(error))
        except LearningStorageError as error:
            self.status.configure(text=str(error))

    def _abort_session(self) -> None:
        if self.session is None:
            return
        self.last_summary = self.session.finish(aborted=True)
        self._show_summary()

    def _show_summary(self) -> None:
        if self.session is None:
            return
        self.last_summary = self.session.summary()
        summary = self.last_summary
        if self._timer_after_id is not None:
            try:
                self.after_cancel(self._timer_after_id)
            except tk.TclError:
                pass
            self._timer_after_id = None
        if self._auto_next_after_id is not None:
            try:
                self.after_cancel(self._auto_next_after_id)
            except Exception:
                pass
            self._auto_next_after_id = None
        self._session_deadline = None
        self.session_panel.grid_forget()
        for child in self.summary_panel.winfo_children():
            child.destroy()
        card = ctk.CTkFrame(
            self.summary_panel, fg_color=COLORS["card"], corner_radius=18,
            border_color=COLORS["border"], border_width=1,
        )
        card.grid(row=0, column=0, sticky="ew", pady=(10, 14))
        ctk.CTkLabel(
            card, text="Sesja zakończona" if not summary.aborted else "Sesja przerwana",
            font=ctk.CTkFont(size=23, weight="bold"), text_color=COLORS["text"],
        ).pack(padx=20, pady=(20, 12))
        ctk.CTkLabel(
            card,
            text=(
                f"Temat: {_TOPIC_LABELS[summary.topic]}\n"
                f"Poprawne odpowiedzi: {summary.correct_count}\n"
                f"Błędne odpowiedzi: {summary.incorrect_count}\n"
                f"Ukończone zadania: {summary.answered_count} / {summary.total_questions}\n"
                f"Skuteczność: {summary.accuracy_percent}%\n"
                f"Poziom: {DIFFICULTY_NAMES[summary.initial_difficulty]} → "
                f"{DIFFICULTY_NAMES[summary.final_difficulty]}\n"
                f"Czas nauki: {summary.elapsed_seconds} s"
            ),
            justify="left", font=ctk.CTkFont(size=14),
            text_color=COLORS["muted"],
        ).pack(anchor="w", padx=25, pady=(0, 22))
        ctk.CTkButton(
            card, text="Wróć do wyboru tematu", height=40, corner_radius=11,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self._return_to_setup,
        ).pack(anchor="w", padx=20, pady=(0, 20))
        self.summary_panel.grid(row=2, column=0, sticky="ew", pady=(0, 22))
        self._show_history()

    def destroy(self) -> None:
        if self._timer_after_id is not None:
            try:
                self.after_cancel(self._timer_after_id)
            except tk.TclError:
                pass
            self._timer_after_id = None
        if self._auto_next_after_id is not None:
            try:
                self.after_cancel(self._auto_next_after_id)
            except tk.TclError:
                pass
            self._auto_next_after_id = None
        super().destroy()

    def _return_to_setup(self) -> None:
        self.summary_panel.grid_forget()
        self.setup_panel.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        self.history_panel.grid(row=4, column=0, sticky="ew", pady=(8, 22))
        self.session = None
        self.last_summary = None
        self._show_history()

    def _update_progress(self) -> None:
        if self.session is None:
            return
        self._progress_text = (
            f"Poprawne: {self.session.correct_count}     "
            f"Błędy: {self.session.incorrect_count}     "
            f"Postęp: {self.session.answered_count}/{self.session.total_questions}"
        )
        self.progress_label.configure(text=self._progress_text)
        self.progress_bar.set(self.session.progress)

    def _play_feedback_sound(self, correct: bool) -> None:
        volume = int(self.preferences.get("sound_volume", 0))
        if not self.preferences.get("sound_enabled") or volume <= 0:
            return
        if sys.platform != "win32":
            self.winfo_toplevel().bell()
            return
        sample_rate = 22050
        frequency = 880 if correct else 330
        amplitude = round(10000 * volume / 100)
        samples = b"".join(
            struct.pack("<h", round(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate)))
            for index in range(round(sample_rate * 0.09))
        )
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(samples)
        try:
            import winsound
            winsound.PlaySound(output.getvalue(), winsound.SND_MEMORY)
        except (ImportError, RuntimeError, TypeError):
            self.winfo_toplevel().bell()

    def _show_history(self) -> None:
        for child in self.history_panel.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self.history_panel, text="Ostatnie odpowiedzi", anchor="w",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=17, pady=(15, 8))
        try:
            history = self.learning_service.get_recent_history(self.user_id, limit=8)
        except LearningStorageError as error:
            ctk.CTkLabel(
                self.history_panel, text=f"Nie udało się wczytać historii: {error}",
                anchor="w", wraplength=600, text_color="#FCA5A5",
            ).pack(fill="x", padx=17, pady=(0, 15))
            return
        if not history:
            text = "Brak historii. Rozpocznij pierwsze ćwiczenie, aby zapisać postępy."
            color = COLORS["muted"]
        else:
            text = "\n".join(
                f"{'✓' if item.correct else '✗'}  {_TOPIC_LABELS.get(Topic(item.topic), item.topic)}"
                f" · {DIFFICULTY_NAMES.get(item.difficulty, f'Poziom {item.difficulty}')} "
                f"· {item.completed_at}"
                for item in history
            )
            color = COLORS["muted"]
        ctk.CTkLabel(
            self.history_panel, text=text, anchor="w", justify="left",
            wraplength=700, font=ctk.CTkFont(size=11), text_color=color,
        ).pack(fill="x", padx=17, pady=(0, 15))
