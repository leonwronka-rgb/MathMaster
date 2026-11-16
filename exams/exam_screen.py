from __future__ import annotations

import math
from collections.abc import Callable

import customtkinter as ctk

from exams.exam_service import (
    SUBJECTS,
    ExamAttempt,
    ExamCompletion,
    ExamError,
    ExamGradingScale,
    ExamService,
    ExamStorageError,
)
from mathematics.topics import DIFFICULTY_LEVELS, DIFFICULTY_NAMES, TOPIC_CATEGORIES
from ui.theme import COLORS


class ExamScreen(ctk.CTkScrollableFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        user_id: int,
        service: ExamService,
        on_gamification_update: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            parent,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.user_id = user_id
        self.service = service
        self.on_gamification_update = on_gamification_update
        self.attempt: ExamAttempt | None = None
        self.completion: ExamCompletion | None = None
        self.current_index = 0
        self._timer_job: str | None = None
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(5, 15))
        ctk.CTkLabel(
            header,
            text="Egzaminy próbne",
            anchor="w",
            font=ctk.CTkFont(size=27, weight="bold"),
            text_color=COLORS["text"],
        ).pack(side="left")
        self.status = ctk.CTkLabel(
            self, text="", anchor="w", text_color=COLORS["muted"], wraplength=700
        )
        self.status.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        self.setup_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.setup_panel.grid(row=2, column=0, sticky="ew")
        self.setup_panel.grid_columnconfigure(0, weight=1)
        self.exam_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.exam_panel.grid(row=2, column=0, sticky="ew")
        self.exam_panel.grid_columnconfigure(0, weight=1)
        self.exam_panel.grid_remove()
        self.result_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.result_panel.grid(row=2, column=0, sticky="ew")
        self.result_panel.grid_columnconfigure(0, weight=1)
        self.result_panel.grid_remove()
        self._build_setup()
        self._load_history()

    def _build_setup(self) -> None:
        card = self._card(self.setup_panel, "Konfiguracja egzaminu")
        card.grid_columnconfigure((0, 1), weight=1, uniform="exam-setup")
        self.subject = self._option(
            card, "Przedmiot", list(SUBJECTS), 0, 0
        )
        self.category = self._option(
            card, "Kategoria", list(TOPIC_CATEGORIES), 0, 1
        )
        self.difficulty = self._option(
            card,
            "Poziom trudności",
            [DIFFICULTY_NAMES[level] for level in DIFFICULTY_LEVELS],
            2,
            0,
        )
        self.question_count = self._option(
            card, "Liczba zadań", ["5", "10", "15", "20", "30"], 2, 1
        )
        self.time_limit = self._option(
            card, "Czas (minuty)", ["5", "10", "15", "20", "30", "45", "60", "90", "120"],
            4, 0,
        )
        self.difficulty.set(DIFFICULTY_NAMES[3])
        self.question_count.set("10")
        self.time_limit.set("30")

        ctk.CTkLabel(
            card,
            text="Progi ocen (procenty): 2, 3, 4, 5, 6 — ustaw wartości rosnąco.",
            anchor="w",
            text_color=COLORS["muted"],
        ).grid(row=4, column=1, sticky="w", padx=(12, 18), pady=(14, 4))
        self.grade_entries: list[ctk.CTkEntry] = []
        scale_row = ctk.CTkFrame(card, fg_color="transparent")
        scale_row.grid(row=5, column=1, sticky="ew", padx=(12, 18), pady=(0, 15))
        for grade, threshold in enumerate((30, 50, 70, 85, 95), start=2):
            entry = ctk.CTkEntry(
                scale_row,
                width=54,
                placeholder_text=str(grade),
                justify="center",
                fg_color=COLORS["surface"],
            )
            entry.insert(0, str(threshold))
            entry.pack(side="left", padx=(0, 5))
            self.grade_entries.append(entry)

        ctk.CTkLabel(
            card,
            text="Przedmiotem jest obecnie matematyka; zadania są losowane z wybranej kategorii.",
            anchor="w",
            wraplength=700,
            text_color=COLORS["muted"],
        ).grid(row=6, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 12))
        ctk.CTkButton(
            card,
            text="Rozpocznij egzamin",
            height=42,
            command=self._start_exam,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).grid(row=7, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 18))

        self.history_card = self._card(self.setup_panel, "Ostatnie egzaminy")
        self.history_card.grid(row=1, column=0, sticky="ew", pady=(0, 12))

    @staticmethod
    def _card(parent: ctk.CTkFrame, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["card"],
            corner_radius=18,
            border_color=COLORS["border"],
            border_width=1,
        )
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card,
            text=title,
            anchor="w",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(15, 8))
        return card

    @staticmethod
    def _option(
        parent: ctk.CTkFrame,
        label: str,
        values: list[str],
        row: int,
        column: int,
    ) -> ctk.CTkOptionMenu:
        ctk.CTkLabel(
            parent, text=label, anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["muted"],
        ).grid(
            row=row, column=column, sticky="ew",
            padx=(18, 8) if column == 0 else (12, 18),
            pady=(12 if row else 0, 4),
        )
        menu = ctk.CTkOptionMenu(
            parent,
            values=values,
            fg_color=COLORS["surface"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        menu.grid(
            row=row + 1, column=column, sticky="ew",
            padx=(18, 8) if column == 0 else (12, 18),
            pady=(0, 2),
        )
        menu.set(values[0])
        return menu

    def _start_exam(self) -> None:
        try:
            scale = ExamGradingScale(
                (
                    int(self.grade_entries[0].get()),
                    int(self.grade_entries[1].get()),
                    int(self.grade_entries[2].get()),
                    int(self.grade_entries[3].get()),
                    int(self.grade_entries[4].get()),
                )
            )
            level = next(
                level for level, label in DIFFICULTY_NAMES.items()
                if label == self.difficulty.get()
            )
            attempt = self.service.start_exam(
                user_id=self.user_id,
                subject=self.subject.get(),
                category=self.category.get(),
                difficulty=level,
                question_count=int(self.question_count.get()),
                time_limit_seconds=int(self.time_limit.get()) * 60,
                grading_scale=scale,
            )
        except (ValueError, ExamStorageError) as error:
            self.status.configure(text=str(error), text_color="#FCA5A5")
            return
        self.attempt = attempt
        self.completion = None
        self.current_index = 0
        self.status.configure(text="")
        self.setup_panel.grid_remove()
        self.result_panel.grid_remove()
        self.exam_panel.grid()
        self._build_attempt_view()
        self._show_question()
        self._tick()

    def _build_attempt_view(self) -> None:
        for child in self.exam_panel.winfo_children():
            child.destroy()
        assert self.attempt is not None
        heading = ctk.CTkFrame(self.exam_panel, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        heading.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            heading,
            text=f"{self.attempt.subject} · {self.attempt.category}",
            anchor="w",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="w")
        self.timer_label = ctk.CTkLabel(
            heading,
            text="",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=COLORS["orange"],
        )
        self.timer_label.grid(row=0, column=1, sticky="e")
        self.progress_label = ctk.CTkLabel(
            self.exam_panel, text="", anchor="w", text_color=COLORS["muted"]
        )
        self.progress_label.grid(row=1, column=0, sticky="ew", pady=(0, 7))
        self.question_card = ctk.CTkFrame(
            self.exam_panel,
            fg_color=COLORS["card"],
            corner_radius=18,
            border_color=COLORS["border"],
            border_width=1,
        )
        self.question_card.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.question_card.grid_columnconfigure(0, weight=1)
        self.question_label = ctk.CTkLabel(
            self.question_card,
            text="",
            anchor="w",
            justify="left",
            wraplength=720,
            font=ctk.CTkFont(size=16),
            text_color=COLORS["text"],
        )
        self.question_label.grid(row=0, column=0, sticky="ew", padx=18, pady=18)
        self.answer_entry = ctk.CTkEntry(
            self.question_card,
            placeholder_text="Wpisz odpowiedź (pozostaw puste, jeśli pomijasz zadanie)",
            height=40,
            fg_color=COLORS["surface"],
        )
        self.answer_entry.grid(
            row=1, column=0, sticky="ew", padx=18, pady=(0, 12)
        )
        self.answer_entry.bind("<KeyRelease>", self._answer_changed)
        self.answer_entry.bind("<<Paste>>", self._paste_answer)
        self.flag_button = ctk.CTkButton(
            self.question_card,
            text="Oznacz do później",
            width=155,
            command=self._toggle_mark,
            fg_color=COLORS["surface"],
            hover_color=COLORS["card_hover"],
        )
        self.flag_button.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 16))

        self.question_nav = ctk.CTkFrame(self.exam_panel, fg_color="transparent")
        self.question_nav.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self.nav_buttons: list[ctk.CTkButton] = []
        for index in range(self.attempt.question_count):
            button = ctk.CTkButton(
                self.question_nav,
                text=str(index + 1),
                width=40,
                height=34,
                command=lambda selected=index: self._goto_question(selected),
                fg_color=COLORS["surface"],
                hover_color=COLORS["card_hover"],
                text_color=COLORS["text"],
            )
            button.grid(row=index // 10, column=index % 10, padx=3, pady=3)
            self.nav_buttons.append(button)

        controls = ctk.CTkFrame(self.exam_panel, fg_color="transparent")
        controls.grid(row=4, column=0, sticky="ew", pady=(0, 15))
        self.previous_button = ctk.CTkButton(
            controls,
            text="← Poprzednie",
            command=lambda: self._goto_question(self.current_index - 1),
            fg_color=COLORS["surface"],
            hover_color=COLORS["card_hover"],
        )
        self.previous_button.pack(side="left")
        self.next_button = ctk.CTkButton(
            controls,
            text="Następne →",
            command=lambda: self._goto_question(self.current_index + 1),
            fg_color=COLORS["surface"],
            hover_color=COLORS["card_hover"],
        )
        self.next_button.pack(side="left", padx=8)
        ctk.CTkButton(
            controls,
            text="Zakończ egzamin",
            command=self._finish_exam,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(side="right")

    def _show_question(self) -> None:
        if self.attempt is None or self.attempt.finished:
            return
        question = self.attempt.questions[self.current_index]
        self.progress_label.configure(
            text=f"Zadanie {self.current_index + 1} z {self.attempt.question_count}"
        )
        self.question_label.configure(text=question.exercise.prompt)
        self.answer_entry.delete(0, "end")
        if question.answer:
            self.answer_entry.insert(0, question.answer)
        self.flag_button.configure(
            text="★ Oznaczono" if question.marked_for_review else "Oznacz do później",
            fg_color=COLORS["accent_soft"] if question.marked_for_review else COLORS["surface"],
        )
        self.previous_button.configure(
            state="normal" if self.current_index > 0 else "disabled"
        )
        self.next_button.configure(
            state="normal"
            if self.current_index + 1 < self.attempt.question_count
            else "disabled"
        )
        self._update_question_buttons()

    def _save_current_answer(self) -> bool:
        if self.attempt is None or self.attempt.finished:
            return False
        try:
            self.attempt.set_answer(self.current_index, self.answer_entry.get())
        except ExamError:
            self._finish_exam()
            return False
        except ValueError as error:
            self.status.configure(text=str(error), text_color="#FCA5A5")
            return False
        self._update_question_buttons()
        return True

    def _answer_changed(self, _event: object) -> None:
        if getattr(_event, "widget", None) is not None:
            self._sync_answer()

    def _paste_answer(self, event: object) -> None:
        if getattr(event, "widget", None) is not None:
            self.after_idle(self._sync_answer)

    def _sync_answer(self) -> None:
        if self.attempt is None or self.attempt.finished:
            return
        try:
            self.attempt.set_answer(self.current_index, self.answer_entry.get())
        except ExamError:
            self._finish_exam()
        except ValueError as error:
            self.status.configure(text=str(error), text_color="#FCA5A5")
        else:
            self.status.configure(text="")
            self._update_question_buttons()

    def _goto_question(self, index: int) -> None:
        if self.attempt is None or self.attempt.finished:
            return
        if not self._save_current_answer():
            return
        if not 0 <= index < self.attempt.question_count:
            return
        self.current_index = index
        self._show_question()

    def _toggle_mark(self) -> None:
        if self.attempt is None or not self._save_current_answer():
            return
        try:
            self.attempt.toggle_marked(self.current_index)
        except ExamError:
            self._finish_exam()
            return
        self._show_question()

    def _update_question_buttons(self) -> None:
        if self.attempt is None:
            return
        for index, (question, button) in enumerate(
            zip(self.attempt.questions, self.nav_buttons)
        ):
            suffix = " ★" if question.marked_for_review else (
                " ✓" if question.answer.strip() else ""
            )
            active = index == self.current_index
            button.configure(
                text=f"{index + 1}{suffix}",
                fg_color=COLORS["accent"] if active else COLORS["surface"],
            )

    def _tick(self) -> None:
        if self.attempt is None or self.attempt.finished:
            return
        remaining = self.attempt.remaining_seconds
        if remaining <= 0:
            self._finish_exam()
            return
        seconds = math.ceil(remaining)
        self.timer_label.configure(
            text=f"Pozostało {seconds // 60:02d}:{seconds % 60:02d}",
            text_color=COLORS["orange"] if seconds > 60 else "#FCA5A5",
        )
        self._timer_job = self.after(200, self._tick)

    def _finish_exam(self) -> None:
        if self.attempt is None:
            return
        if self._timer_job is not None:
            try:
                self.after_cancel(self._timer_job)
            except ctk.TclError:
                pass
            self._timer_job = None
        if not self.attempt.finished:
            try:
                self.attempt.set_answer(self.current_index, self.answer_entry.get())
            except ExamError:
                pass
            except ValueError as error:
                self.status.configure(text=str(error), text_color="#FCA5A5")
                if not self.attempt.expired:
                    return
        try:
            self.completion = self.service.complete_exam(self.user_id, self.attempt)
        except (ExamStorageError, ValueError) as error:
            self.exam_panel.grid_remove()
            self.result_panel.grid()
            self._clear_result_panel()
            ctk.CTkLabel(
                self.result_panel,
                text=f"Nie udało się zapisać egzaminu: {error}",
                anchor="w",
                wraplength=700,
                text_color="#FCA5A5",
            ).grid(row=0, column=0, sticky="ew", pady=(0, 12))
            ctk.CTkButton(
                self.result_panel,
                text="Ponów zapis",
                command=self._finish_exam,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
            ).grid(row=1, column=0, sticky="w")
            return
        self.exam_panel.grid_remove()
        self.setup_panel.grid_remove()
        self.result_panel.grid()
        self._render_result(self.completion)
        if self.on_gamification_update is not None:
            self.on_gamification_update()

    def _render_result(self, completion: ExamCompletion) -> None:
        self._clear_result_panel()
        result = completion.result
        summary = self._card(self.result_panel, "Wynik egzaminu")
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(
            summary,
            text=(
                f"{'Egzamin zdany' if result.passed else 'Egzamin niezaliczony'}\n"
                f"Punkty: {result.correct_count}/{result.question_count}  ·  "
                f"Skuteczność: {result.score_percent:.1f}%  ·  Ocena: {result.grade}\n"
                f"Czas: {self._format_duration(result.duration_seconds)}"
                f" / {self._format_duration(result.time_limit_seconds)}"
            ),
            anchor="w",
            justify="left",
            text_color=COLORS["success"] if result.passed else "#FCA5A5",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        comparison = (
            "To pierwszy egzamin w tej kategorii."
            if completion.previous_result is None
            else self._comparison_text(completion)
        )
        ctk.CTkLabel(
            summary,
            text=comparison,
            anchor="w",
            text_color=COLORS["muted"],
        ).grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))
        reward = completion.reward
        reward_text = (
            f"+{reward.xp_awarded} XP"
            + (
                f"  ·  Awans na poziom {reward.level}!"
                if reward.level > reward.old_level
                else ""
            )
        )
        ctk.CTkLabel(
            summary,
            text=reward_text,
            anchor="w",
            text_color=COLORS["accent"],
        ).grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 14))

        details = self._card(self.result_panel, "Szczegółowe omówienie")
        details.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        details_content = ctk.CTkFrame(details, fg_color="transparent")
        details_content.grid(row=1, column=0, sticky="ew")
        details_content.grid_columnconfigure(0, weight=1)
        for item in result.answers:
            status = "✓ Poprawnie" if item.correct else (
                "— Bez odpowiedzi" if not item.submitted_answer.strip() else "✗ Błędnie"
            )
            color = COLORS["success"] if item.correct else "#FCA5A5"
            review = "  ·  oznaczone do później" if item.marked_for_review else ""
            ctk.CTkLabel(
                details_content,
                text=(
                    f"Zadanie {item.question_number}  ·  {status}{review}\n"
                    f"{item.question}\n"
                    f"Twoja odpowiedź: {item.submitted_answer or '—'}\n"
                    f"Poprawna odpowiedź: {item.correct_answer}\n"
                    f"{item.solution}"
                ),
                anchor="w",
                justify="left",
                wraplength=760,
                text_color=color,
            ).pack(fill="x", padx=16, pady=(0, 10))
            ctk.CTkFrame(details_content, height=1, fg_color=COLORS["border"]).pack(
                fill="x", padx=16, pady=(0, 9)
            )
        ctk.CTkButton(
            self.result_panel,
            text="Wróć do konfiguracji",
            command=self._back_to_setup,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).grid(row=2, column=0, sticky="w", pady=(0, 15))
        self._load_history()

    def _comparison_text(self, completion: ExamCompletion) -> str:
        previous = completion.previous_result
        if previous is None:
            return "To pierwszy egzamin w tej kategorii."
        difference = completion.score_difference or 0
        if difference > 0:
            change = f"wzrost o {difference:.1f} p.p."
        elif difference < 0:
            change = f"spadek o {abs(difference):.1f} p.p."
        else:
            change = "bez zmiany"
        return (
            f"Poprzedni wynik w kategorii {previous.category}: "
            f"{previous.score_percent:.1f}% (ocena {previous.grade}). "
            f"Zmiana: {change}."
        )

    def _load_history(self) -> None:
        for child in self.history_card.winfo_children():
            if int(child.grid_info().get("row", -1)) > 0:
                child.destroy()
        try:
            results = self.service.get_recent_results(self.user_id, 5)
        except ExamStorageError as error:
            ctk.CTkLabel(
                self.history_card,
                text=str(error),
                anchor="w",
                text_color="#FCA5A5",
            ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 14))
            return
        if not results:
            ctk.CTkLabel(
                self.history_card,
                text="Nie masz jeszcze zapisanych egzaminów.",
                anchor="w",
                text_color=COLORS["muted"],
            ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 14))
            return
        for row, item in enumerate(results, start=1):
            ctk.CTkLabel(
                self.history_card,
                text=(
                    f"{item.completed_at[:16]}  ·  {item.category}  ·  "
                    f"{item.correct_count}/{item.question_count} pkt  ·  "
                    f"{item.score_percent:.1f}%  ·  ocena {item.grade}"
                ),
                anchor="w",
                text_color=COLORS["success"] if item.passed else "#FCA5A5",
            ).grid(row=row, column=0, sticky="ew", padx=18, pady=(0, 8))

    def _back_to_setup(self) -> None:
        self.result_panel.grid_remove()
        self.setup_panel.grid()
        self._load_history()

    def _clear_result_panel(self) -> None:
        for child in self.result_panel.winfo_children():
            child.destroy()

    @staticmethod
    def _format_duration(seconds: int) -> str:
        minutes, remaining = divmod(seconds, 60)
        return f"{minutes} min {remaining:02d} s"
