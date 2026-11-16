from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox
from urllib.parse import urlsplit

import customtkinter as ctk

from exercises.custom_tasks import (
    MAX_BUNDLE_BYTES,
    CustomTask,
    CustomTaskError,
    CustomTaskService,
    CustomTaskStorageError,
    PracticeExercise,
    TaskBundlePreview,
    TaskDownloadError,
)
from mathematics.topics import DIFFICULTY_NAMES, TOPIC_CATEGORIES, Topic
from ui.theme import COLORS

_ALL = "Wszystkie"
_DIFFICULTY_OPTIONS = tuple(DIFFICULTY_NAMES.values())
_DIFFICULTY_TO_LEVEL = {
    label: level for level, label in DIFFICULTY_NAMES.items()
}
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
    Topic.GRAPH_POINT: "Wykresy funkcji",
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


class CustomTaskScreen(ctk.CTkScrollableFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        user_id: int,
        service: CustomTaskService,
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
        self.sets = ()
        self.tasks: tuple[CustomTask, ...] = ()
        self.selected_task: CustomTask | None = None
        self.queue: tuple[PracticeExercise, ...] = ()
        self.current_exercise: PracticeExercise | None = None
        self.queue_index = 0
        self.session_key = ""
        self.answered = False
        self.hint_index = 0
        self.correct_count = 0
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Własne zadania matematyczne",
            anchor="w",
            font=ctk.CTkFont(size=27, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", pady=(4, 4))
        ctk.CTkLabel(
            self,
            text="Twórz zadania, importuj zestawy JSON i ćwicz z własną biblioteką.",
            anchor="w",
            text_color=COLORS["muted"],
        ).grid(row=1, column=0, sticky="ew", pady=(0, 14))

        self._build_library_panel()
        self._build_generator_panel()
        self._build_practice_panel()
        self.status = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            wraplength=900,
            text_color=COLORS["muted"],
        )
        self.status.grid(row=5, column=0, sticky="ew", pady=(8, 14))
        self.refresh()

    def _build_library_panel(self) -> None:
        library = ctk.CTkFrame(
            self,
            fg_color=COLORS["card"],
            corner_radius=18,
            border_color=COLORS["border"],
            border_width=1,
        )
        library.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        library.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            library,
            text="Moja biblioteka",
            anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        filters = ctk.CTkFrame(library, fg_color="transparent")
        filters.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        filters.grid_columnconfigure((0, 1, 2), weight=1)
        self.category_filter = ctk.CTkOptionMenu(
            filters,
            values=[_ALL, *TOPIC_CATEGORIES.keys()],
            command=lambda _: self.refresh_tasks(),
        )
        self.category_filter.set(_ALL)
        self.category_filter.grid(row=0, column=0, sticky="ew", padx=3)
        self.set_filter = ctk.CTkOptionMenu(
            filters, values=[_ALL], command=lambda _: self.refresh_tasks()
        )
        self.set_filter.set(_ALL)
        self.set_filter.grid(row=0, column=1, sticky="ew", padx=3)
        self.search_entry = ctk.CTkEntry(filters, placeholder_text="Szukaj zadania…")
        self.search_entry.grid(row=0, column=2, sticky="ew", padx=3)
        self.search_entry.bind("<KeyRelease>", lambda _: self.refresh_tasks())

        self.task_list = ctk.CTkScrollableFrame(
            library, fg_color=COLORS["surface"], height=150
        )
        self.task_list.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        self.task_list.grid_columnconfigure(0, weight=1)
        buttons = ctk.CTkFrame(library, fg_color="transparent")
        buttons.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))
        buttons.grid_columnconfigure((0, 1, 2, 3), weight=1)
        actions = (
            ("＋ Nowe zadanie", self._open_create_dialog),
            ("＋ Zestaw", self._create_set),
            ("Edytuj", self._edit_selected),
            ("Usuń", self._delete_selected),
            ("Import JSON", self._import_file),
            ("Pobierz HTTPS", self._download_url),
            ("Eksportuj widok", self._export),
            ("Rozwiąż wybrane", self._practice_selected),
        )
        for index, (label, command) in enumerate(actions):
            ctk.CTkButton(
                buttons,
                text=label,
                command=command,
                fg_color=COLORS["accent"] if label == "Rozwiąż wybrane" else COLORS["surface"],
                hover_color=COLORS["accent_hover"] if label == "Rozwiąż wybrane" else COLORS["card_hover"],
            ).grid(
                row=index // 4,
                column=index % 4,
                padx=3,
                pady=3,
                sticky="ew",
            )
        self.details = ctk.CTkLabel(
            library,
            text="Wybierz zadanie z listy, aby zobaczyć jego treść i pochodzenie.",
            anchor="w",
            justify="left",
            wraplength=900,
            text_color=COLORS["muted"],
        )
        self.details.grid(row=4, column=0, sticky="ew", padx=14, pady=(4, 12))

    def _build_generator_panel(self) -> None:
        panel = ctk.CTkFrame(
            self,
            fg_color=COLORS["card"],
            corner_radius=18,
            border_color=COLORS["border"],
            border_width=1,
        )
        panel.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        panel.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        ctk.CTkLabel(
            panel,
            text="Generator ćwiczeń",
            anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, columnspan=5, sticky="ew", padx=14, pady=(12, 6))
        self.generator_category = ctk.CTkOptionMenu(
            panel,
            values=list(TOPIC_CATEGORIES),
            command=self._generator_category_changed,
        )
        self.generator_category.set(next(iter(TOPIC_CATEGORIES)))
        self.generator_category.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 12))
        self.generator_topic = ctk.CTkOptionMenu(panel, values=[])
        self.generator_topic.grid(row=1, column=1, sticky="ew", padx=5, pady=(0, 12))
        self.generator_difficulty = ctk.CTkOptionMenu(
            panel, values=list(_DIFFICULTY_OPTIONS)
        )
        self.generator_difficulty.set(DIFFICULTY_NAMES[1])
        self.generator_difficulty.grid(row=1, column=2, sticky="ew", padx=5, pady=(0, 12))
        self.generator_count = ctk.CTkEntry(
            panel, placeholder_text="Liczba (1–100)", width=90
        )
        self.generator_count.insert(0, "10")
        self.generator_count.grid(row=1, column=3, sticky="ew", padx=5, pady=(0, 12))
        ctk.CTkButton(
            panel,
            text="Losuj zestaw",
            command=self._generate,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).grid(row=1, column=4, sticky="ew", padx=5, pady=(0, 12))
        self._generator_category_changed(next(iter(TOPIC_CATEGORIES)))

    def _build_practice_panel(self) -> None:
        panel = ctk.CTkFrame(
            self,
            fg_color=COLORS["card"],
            corner_radius=18,
            border_color=COLORS["border"],
            border_width=1,
        )
        panel.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        panel.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            panel,
            text="Ćwiczenie",
            anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        self.practice_counter = ctk.CTkLabel(
            panel, text="Wybierz zadanie lub wylosuj zestaw.", anchor="w",
            text_color=COLORS["muted"],
        )
        self.practice_counter.grid(row=1, column=0, sticky="ew", padx=14, pady=4)
        self.practice_source = ctk.CTkLabel(
            panel, text="", anchor="w", text_color=COLORS["blue"]
        )
        self.practice_source.grid(row=2, column=0, sticky="ew", padx=14, pady=3)
        self.question = ctk.CTkLabel(
            panel,
            text="",
            anchor="w",
            justify="left",
            wraplength=900,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text"],
        )
        self.question.grid(row=3, column=0, sticky="ew", padx=14, pady=8)
        self.choices = ctk.CTkOptionMenu(
            panel, values=["—"], command=self._choice_selected
        )
        self.choices.grid(row=4, column=0, sticky="ew", padx=14, pady=4)
        self.answer = ctk.CTkEntry(
            panel, placeholder_text="Wpisz odpowiedź matematyczną lub wybierz z listy…"
        )
        self.answer.grid(row=5, column=0, sticky="ew", padx=14, pady=4)
        controls = ctk.CTkFrame(panel, fg_color="transparent")
        controls.grid(row=6, column=0, sticky="ew", padx=12, pady=4)
        self.hint_button = ctk.CTkButton(
            controls, text="Podpowiedź", command=self._show_hint,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
        )
        self.hint_button.pack(side="left", padx=3)
        self.check_button = ctk.CTkButton(
            controls, text="Sprawdź odpowiedź", command=self._check_answer,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        )
        self.check_button.pack(side="left", padx=3)
        self.next_button = ctk.CTkButton(
            controls, text="Następne", command=self._next_exercise,
            state="disabled", fg_color=COLORS["surface"],
            hover_color=COLORS["card_hover"],
        )
        self.next_button.pack(side="left", padx=3)
        self.feedback = ctk.CTkLabel(
            panel, text="", anchor="w", justify="left", wraplength=900,
            text_color=COLORS["muted"],
        )
        self.feedback.grid(row=7, column=0, sticky="ew", padx=14, pady=(4, 12))

    def refresh(self) -> None:
        try:
            self.sets = self.service.list_sets(self.user_id)
            self.set_filter.configure(values=[_ALL, *(item.name for item in self.sets)])
            self.refresh_tasks()
        except (CustomTaskStorageError, CustomTaskError) as error:
            self._message(str(error), error=True)

    def refresh_tasks(self) -> None:
        for child in self.task_list.winfo_children():
            child.destroy()
        category = self.category_filter.get()
        selected_set_name = self.set_filter.get()
        selected_set = next(
            (item for item in self.sets if item.name == selected_set_name), None
        )
        try:
            self.tasks = self.service.list_tasks(
                self.user_id,
                category=None if category == _ALL else category,
                set_id=selected_set.id if selected_set else None,
                search=self.search_entry.get(),
            )
        except (CustomTaskError, CustomTaskStorageError) as error:
            self._message(str(error), error=True)
            return
        for task in self.tasks:
            button = ctk.CTkButton(
                self.task_list,
                text=f"{task.name}  ·  {task.category}  ·  {task.source_label}",
                anchor="w",
                fg_color=COLORS["surface"],
                hover_color=COLORS["card_hover"],
                command=lambda selected=task: self._select_task(selected),
            )
            button.pack(fill="x", padx=3, pady=2)
        if not self.tasks:
            ctk.CTkLabel(
                self.task_list,
                text="Brak zadań w tym widoku. Utwórz zadanie lub zaimportuj zestaw.",
                text_color=COLORS["muted"],
            ).pack(fill="x", padx=8, pady=14)
        names = [item.name for item in self.sets]
        if selected_set_name not in {_ALL, *names}:
            self.set_filter.set(_ALL)
        if self.selected_task and all(
            item.id != self.selected_task.id for item in self.tasks
        ):
            self.selected_task = None

    def _select_task(self, task: CustomTask) -> None:
        self.selected_task = task
        self.details.configure(
            text=(
                f"{task.name}\n{task.question}\n\nKategoria: {task.category} · "
                f"Temat: {_TOPIC_LABELS[task.topic]} · Poziom: "
                f"{DIFFICULTY_NAMES[task.difficulty]} · Nagroda: {task.xp_points} XP\n"
                f"Zestaw: {task.set_name} · Pochodzenie: {task.source_label}\n"
                f"Wyjaśnienie: {task.explanation}\n"
                f"Podpowiedzi: {' | '.join(task.hints) if task.hints else 'brak'}"
            )
        )
        selected_set = next((item for item in self.sets if item.id == task.set_id), None)
        if selected_set and selected_set.source_kind == "url":
            self.details.configure(
                text=(
                    self.details.cget("text")
                    + f"\nŹródło URL: {selected_set.source_url}"
                    + f" · Pobrano: {selected_set.downloaded_at or 'brak danych'}"
                )
            )
        exercise = PracticeExercise(
                task.question,
                task.answer,
                task.explanation,
                task.category,
                task.topic,
                task.difficulty,
                task.xp_points,
                task.hints,
                task.choices,
                task.source_label,
                task.id,
                task.set_name,
                task.name,
            )
        self.queue = (exercise,)
        self.session_key = str(uuid.uuid4())
        self._load_practice(
            exercise,
            index=0,
            count=1,
        )

    def _generator_category_changed(self, category: str) -> None:
        topics = TOPIC_CATEGORIES[category]
        labels = [_TOPIC_LABELS[topic] for topic in topics]
        self.generator_topic.configure(values=labels)
        self.generator_topic.set(labels[0])

    def _generate(self) -> None:
        try:
            count = int(self.generator_count.get())
            category = self.generator_category.get()
            topic_label = self.generator_topic.get()
            topic = next(
                item for item in TOPIC_CATEGORIES[category]
                if _TOPIC_LABELS[item] == topic_label
            )
            difficulty = _DIFFICULTY_TO_LEVEL[self.generator_difficulty.get()]
            self.queue = self.service.generate_exercises(
                self.user_id,
                category=category,
                topic=topic,
                difficulty=difficulty,
                count=count,
            )
            self.queue_index = 0
            self.session_key = str(uuid.uuid4())
            self.correct_count = 0
            self._load_practice(self.queue[0], index=0, count=len(self.queue))
            custom_count = sum(item.task_id is not None for item in self.queue)
            self._message(
                f"Wylosowano {len(self.queue)} zadań, w tym {custom_count} "
                "z Twojej biblioteki."
            )
        except (ValueError, StopIteration, CustomTaskError, CustomTaskStorageError) as error:
            self._message(str(error), error=True)

    def _practice_selected(self) -> None:
        if self.selected_task is None:
            self._message("Najpierw wybierz zadanie z biblioteki.", error=True)
            return
        self._select_task(self.selected_task)

    def _load_practice(
        self, exercise: PracticeExercise, *, index: int, count: int
    ) -> None:
        if not self.session_key:
            self.session_key = str(uuid.uuid4())
        self.current_exercise = exercise
        self.queue_index = index
        self.answered = False
        self.hint_index = 0
        self.question.configure(text=exercise.question)
        self.practice_counter.configure(text=f"Zadanie {index + 1} z {count}")
        self.practice_source.configure(
            text=f"{exercise.source_label} · {exercise.set_name}"
        )
        if exercise.choices:
            self.choices.configure(values=list(exercise.choices))
            self.choices.set(exercise.choices[0])
            self.answer.delete(0, "end")
            self.answer.insert(0, exercise.choices[0])
            self.choices.grid()
        else:
            self.choices.grid_remove()
            self.answer.delete(0, "end")
        self.feedback.configure(text="")
        self.check_button.configure(state="normal", text="Sprawdź odpowiedź")
        self.next_button.configure(
            state="normal" if index + 1 < count else "disabled"
        )
        self.hint_button.configure(
            state="normal" if exercise.hints else "disabled"
        )

    def _show_hint(self) -> None:
        exercise = getattr(self, "current_exercise", None)
        if exercise is None or not exercise.hints:
            return
        hint = exercise.hints[min(self.hint_index, len(exercise.hints) - 1)]
        self.hint_index += 1
        self.feedback.configure(text=f"Podpowiedź: {hint}")

    def _choice_selected(self, choice: str) -> None:
        self.answer.delete(0, "end")
        self.answer.insert(0, choice)

    def _check_answer(self) -> None:
        if self.current_exercise is None or self.answered:
            return
        try:
            result = self.service.answer_exercise(
                self.user_id,
                self.current_exercise,
                self.answer.get(),
                source_key=f"{self.session_key}:{self.queue_index}",
            )
            self.answered = True
            self.correct_count += int(result.correct)
            verdict = "Poprawna odpowiedź." if result.correct else "Odpowiedź niepoprawna."
            self.feedback.configure(
                text=(
                    f"{verdict} Odpowiedź: {result.answer}\n"
                    f"{result.explanation}\nŹródło: {result.source_label} · "
                    f"XP: +{result.xp_awarded} · Łącznie: {result.total_xp}"
                    f"{' · Awans!' if result.leveled_up else ''}"
                ),
                text_color=COLORS["success"] if result.correct else "#FCA5A5",
            )
            self.check_button.configure(state="disabled", text="Sprawdzone")
            if self.queue_index + 1 < len(self.queue):
                self.next_button.configure(state="normal")
            else:
                self.practice_counter.configure(
                    text=f"Postęp sesji: {self.correct_count} poprawnych odpowiedzi."
                )
            if self.on_gamification_update:
                self.on_gamification_update()
            if self.current_exercise.task_id is not None:
                self.refresh()
        except (CustomTaskError, CustomTaskStorageError) as error:
            self._message(str(error), error=True)

    def _next_exercise(self) -> None:
        if not self.answered:
            self._message("Najpierw sprawdź odpowiedź.", error=True)
            return
        self.queue_index += 1
        if self.queue_index >= len(self.queue):
            self.next_button.configure(state="disabled")
            return
        self._load_practice(
            self.queue[self.queue_index],
            index=self.queue_index,
            count=len(self.queue),
        )

    def _open_create_dialog(self, task: CustomTask | None = None) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Edytuj zadanie" if task else "Nowe zadanie")
        dialog.geometry("650x760")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)
        labels = ("Nazwa", "Treść zadania", "Poprawna odpowiedź", "Wyjaśnienie")
        inputs: dict[str, ctk.CTkTextbox | ctk.CTkEntry] = {}
        keys = ("name", "question", "answer", "explanation")
        heights = (35, 85, 45, 90)
        row = 0
        for label, key, height in zip(labels, keys, heights):
            ctk.CTkLabel(dialog, text=label, anchor="w").grid(
                row=row, column=0, sticky="ew", padx=16, pady=(8, 2)
            )
            row += 1
            if key in {"question", "explanation"}:
                field = ctk.CTkTextbox(dialog, height=height)
            else:
                field = ctk.CTkEntry(dialog, height=height)
            field.grid(row=row, column=0, sticky="ew", padx=16, pady=2)
            inputs[key] = field
            row += 1

        category = ctk.CTkOptionMenu(
            dialog,
            values=list(TOPIC_CATEGORIES),
        )
        category.grid(row=row, column=0, sticky="ew", padx=16, pady=5)
        row += 1
        topic = ctk.CTkOptionMenu(dialog, values=[])
        topic.grid(row=row, column=0, sticky="ew", padx=16, pady=5)
        row += 1
        difficulty = ctk.CTkOptionMenu(dialog, values=list(_DIFFICULTY_OPTIONS))
        difficulty.grid(row=row, column=0, sticky="ew", padx=16, pady=5)
        row += 1
        xp = ctk.CTkEntry(dialog, placeholder_text="Punkty XP (0–1000)")
        xp.grid(row=row, column=0, sticky="ew", padx=16, pady=5)
        row += 1
        hints = ctk.CTkEntry(dialog, placeholder_text="Podpowiedzi, oddzielone średnikiem")
        hints.grid(row=row, column=0, sticky="ew", padx=16, pady=5)
        row += 1
        choices = ctk.CTkEntry(dialog, placeholder_text="Odpowiedzi do wyboru, oddzielone średnikiem")
        choices.grid(row=row, column=0, sticky="ew", padx=16, pady=5)
        row += 1
        selected_set = self._selected_set()
        set_menu = ctk.CTkOptionMenu(
            dialog,
            values=[item.name for item in self.sets] or ["Moje zadania"],
        )
        set_menu.grid(row=row, column=0, sticky="ew", padx=16, pady=5)
        if selected_set:
            set_menu.set(selected_set.name)
        row += 1
        feedback = ctk.CTkLabel(dialog, text="", anchor="w", text_color="#FCA5A5")
        feedback.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        row += 1

        def category_changed(selected: str) -> None:
            topic_values = TOPIC_CATEGORIES[selected]
            topic.configure(values=[_TOPIC_LABELS[item] for item in topic_values])
            topic.set(_TOPIC_LABELS[topic_values[0]])

        category.configure(command=category_changed)

        if task:
            for key, field in inputs.items():
                value = getattr(task, key)
                if isinstance(field, ctk.CTkTextbox):
                    field.insert("1.0", value)
                else:
                    field.insert(0, value)
            category.set(task.category)
            category_changed(task.category)
            topic.set(_TOPIC_LABELS[task.topic])
            difficulty.set(DIFFICULTY_NAMES[task.difficulty])
            xp.insert(0, str(task.xp_points))
            hints.insert(0, "; ".join(task.hints))
            choices.insert(0, "; ".join(task.choices))
        else:
            category.set("Arytmetyka")
            category_changed("Arytmetyka")
            difficulty.set(DIFFICULTY_NAMES[1])
            xp.insert(0, "5")

        def get_text(field: ctk.CTkTextbox | ctk.CTkEntry) -> str:
            if isinstance(field, ctk.CTkTextbox):
                return field.get("1.0", "end").strip()
            return field.get().strip()

        def save() -> None:
            try:
                task_category = category.get()
                selected_topic = next(
                    item
                    for item in TOPIC_CATEGORIES[task_category]
                    if _TOPIC_LABELS[item] == topic.get()
                )
                chosen_set = next(
                    (item for item in self.sets if item.name == set_menu.get()),
                    None,
                )
                values = {
                    "name": get_text(inputs["name"]),
                    "question": get_text(inputs["question"]),
                    "answer": get_text(inputs["answer"]),
                    "explanation": get_text(inputs["explanation"]),
                    "category": task_category,
                    "topic": selected_topic,
                    "difficulty": _DIFFICULTY_TO_LEVEL[difficulty.get()],
                    "xp_points": int(xp.get()),
                    "hints": tuple(
                        item.strip() for item in hints.get().split(";") if item.strip()
                    ),
                    "choices": tuple(
                        item.strip() for item in choices.get().split(";") if item.strip()
                    ),
                    "set_id": chosen_set.id if chosen_set else None,
                }
                if task:
                    values["id"] = task.external_id
                    self.service.update_task(self.user_id, task.id, **values)
                else:
                    self.service.create_task(self.user_id, **values)
                dialog.destroy()
                self.refresh()
                self._message("Zadanie zapisano.")
            except (ValueError, CustomTaskError, CustomTaskStorageError) as error:
                feedback.configure(text=str(error))

        ctk.CTkButton(
            dialog,
            text="Zapisz",
            command=save,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).grid(row=row, column=0, sticky="ew", padx=16, pady=(6, 14))

    def _edit_selected(self) -> None:
        if self.selected_task is None:
            self._message("Wybierz zadanie z listy.", error=True)
            return
        self._open_create_dialog(self.selected_task)

    def _delete_selected(self) -> None:
        if self.selected_task is None:
            self._message("Wybierz zadanie z listy.", error=True)
            return
        if not messagebox.askyesno(
            "Usuń zadanie?",
            "Zadanie zostanie usunięte z biblioteki. Historia prób pozostanie.",
            parent=self,
        ):
            return
        try:
            self.service.delete_task(self.user_id, self.selected_task.id)
            self.selected_task = None
            self.refresh()
        except (CustomTaskError, CustomTaskStorageError) as error:
            self._message(str(error), error=True)

    def _create_set(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Nowy zestaw zadań")
        dialog.geometry("420x190")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        name = ctk.CTkEntry(dialog, placeholder_text="Nazwa zestawu")
        name.pack(fill="x", padx=16, pady=(16, 8))
        category = ctk.CTkOptionMenu(dialog, values=list(TOPIC_CATEGORIES))
        category.pack(fill="x", padx=16, pady=8)
        error = ctk.CTkLabel(dialog, text="", text_color="#FCA5A5")
        error.pack(fill="x", padx=16, pady=3)

        def save() -> None:
            try:
                self.service.create_set(self.user_id, name.get(), category.get())
                dialog.destroy()
                self.refresh()
                self._message("Utworzono zestaw.")
            except (CustomTaskError, CustomTaskStorageError) as exception:
                error.configure(text=str(exception))

        ctk.CTkButton(
            dialog, text="Utwórz zestaw", command=save,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        ).pack(fill="x", padx=16, pady=(4, 14))

    def _import_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Importuj zestaw zadań",
            filetypes=(("Pliki JSON", "*.json"), ("Wszystkie pliki", "*.*")),
        )
        if not path:
            return
        try:
            file_path = Path(path)
            if file_path.stat().st_size > MAX_BUNDLE_BYTES:
                raise CustomTaskError("Plik przekracza limit 5 MB.")
            content = file_path.read_text(encoding="utf-8-sig")
            preview = self.service.preview_import(
                content,
                self.user_id,
                source_kind="file",
                source=file_path.name,
            )
            self._show_import_preview(preview)
        except (OSError, UnicodeError, CustomTaskError, CustomTaskStorageError) as error:
            self._message(str(error), error=True)

    def _download_url(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Pobierz zestaw z HTTPS")
        dialog.geometry("620x200")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        url_entry = ctk.CTkEntry(
            dialog, placeholder_text="https://example.org/tasks.json"
        )
        url_entry.pack(fill="x", padx=16, pady=(16, 8))
        warning = ctk.CTkLabel(
            dialog,
            text="Pobierany jest wyłącznie JSON. Skrypty i kod nie są uruchamiane.",
            anchor="w",
            wraplength=580,
            text_color=COLORS["muted"],
        )
        warning.pack(fill="x", padx=16, pady=4)
        status = ctk.CTkLabel(dialog, text="", anchor="w", text_color="#FCA5A5")
        status.pack(fill="x", padx=16, pady=4)

        def download() -> None:
            url = url_entry.get().strip()
            try:
                fetched = self.service.fetch_json(url)
                host = urlsplit(fetched.final_url).hostname or ""
                if not self._trusted_host(host) and not messagebox.askyesno(
                    "Nieznane źródło",
                    f"Źródło {host} nie należy do znanej listy repozytoriów. "
                    "Dane zostaną potraktowane wyłącznie jako tekst JSON. Kontynuować?",
                    parent=dialog,
                ):
                    return
                preview = self.service.preview_import(
                    fetched.content,
                    self.user_id,
                    source_kind="url",
                    source=fetched.source_name,
                    source_url=fetched.final_url,
                    downloaded_at=fetched.downloaded_at,
                )
                dialog.destroy()
                self._show_import_preview(preview)
            except (TaskDownloadError, CustomTaskError, CustomTaskStorageError) as error:
                status.configure(text=str(error))

        ctk.CTkButton(
            dialog, text="Pobierz i podgląd", command=download,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        ).pack(fill="x", padx=16, pady=(8, 14))

    @staticmethod
    def _trusted_host(host: str) -> bool:
        host = host.casefold().rstrip(".")
        return any(
            host == trusted or host.endswith(f".{trusted}")
            for trusted in (
                "github.com",
                "githubusercontent.com",
                "gitlab.com",
                "gitlabusercontent.com",
                "codeberg.org",
            )
        )

    def _show_import_preview(self, preview: TaskBundlePreview) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Podgląd importu")
        dialog.geometry("760x640")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(1, weight=1)
        downloaded = preview.downloaded_at or "Import z pliku lokalnego"
        source = preview.source_url or preview.source
        warning = (
            "\nUwaga: ten zestaw został już wcześniej zaimportowany."
            if preview.duplicate_set else ""
        )
        ctk.CTkLabel(
            dialog,
            text=(
                f"{preview.name}\nŹródło: {source or 'nieznane'}\n"
                f"Kategoria: {preview.category} · Data pobrania: {downloaded}\n"
                f"Rekordy poprawne: {preview.valid_count} · Błędne: "
                f"{preview.invalid_count} · Duplikaty: {preview.duplicate_count}"
                f"{warning}"
            ),
            anchor="w",
            justify="left",
            wraplength=700,
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        rows = ctk.CTkScrollableFrame(dialog, fg_color=COLORS["surface"])
        rows.grid(row=1, column=0, sticky="nsew", padx=14, pady=6)
        rows.grid_columnconfigure(0, weight=1)
        selections: dict[int, ctk.CTkCheckBox] = {}
        for record in preview.records:
            if record.valid and record.task is not None:
                item = record.task
                row = ctk.CTkFrame(rows, fg_color=COLORS["card"], corner_radius=9)
                row.pack(fill="x", padx=4, pady=3)
                checkbox = ctk.CTkCheckBox(row, text="")
                checkbox.select()
                checkbox.pack(side="left", padx=8)
                selections[record.index] = checkbox
                ctk.CTkLabel(
                    row,
                    text=(
                        f"{item['name']} · {item['category']} · "
                        f"{item['question'][:100]} · odp.: {item['answer'][:35]} · "
                        f"{item['explanation'][:55]}"
                    ),
                    anchor="w",
                    wraplength=620,
                ).pack(side="left", fill="x", expand=True, padx=4, pady=7)
            else:
                issue = "; ".join(record.errors) if record.errors else "Duplikat — pominięty."
                preview_text = ""
                if record.task:
                    preview_text = f"{record.task['name']}: {record.task['question'][:100]} · "
                ctk.CTkLabel(
                    rows,
                    text=f"Rekord {record.index + 1}: {preview_text}{issue}",
                    anchor="w",
                    wraplength=690,
                    text_color="#FCA5A5",
                ).pack(fill="x", padx=8, pady=5)
        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 14))
        buttons.grid_columnconfigure((0, 1), weight=1)

        def commit() -> None:
            selected = {
                index for index, checkbox in selections.items()
                if checkbox.get()
            }
            try:
                result = self.service.import_preview(
                    self.user_id, preview, selected_indices=selected
                )
                dialog.destroy()
                self.refresh()
                self._message(
                    f"Zaimportowano {result.imported}; pominięto błędnych: "
                    f"{result.invalid}, duplikatów: {result.duplicates}."
                )
            except (CustomTaskError, CustomTaskStorageError) as error:
                self._message(str(error), error=True)

        ctk.CTkButton(
            buttons,
            text="Importuj zaznaczone poprawne",
            command=commit,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).grid(row=0, column=0, sticky="ew", padx=4)
        ctk.CTkButton(
            buttons,
            text="Anuluj",
            command=dialog.destroy,
            fg_color=COLORS["surface"],
            hover_color=COLORS["card_hover"],
        ).grid(row=0, column=1, sticky="ew", padx=4)

    def _export(self) -> None:
        category = self.category_filter.get()
        selected_set = self._selected_set()
        if category != _ALL and selected_set:
            # A set is a narrower export selection than the category filter.
            category = None
        else:
            category = None if category == _ALL else category
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Eksportuj własne zadania",
            defaultextension=".json",
            filetypes=(("Pliki JSON", "*.json"),),
        )
        if not path:
            return
        try:
            content = self.service.export_json(
                self.user_id,
                category=category,
                set_id=selected_set.id if selected_set else None,
            )
            if len(content.encode("utf-8")) > MAX_BUNDLE_BYTES:
                raise CustomTaskError("Eksport przekracza limit 5 MB.")
            Path(path).write_text(content, encoding="utf-8")
            self._message("Zestaw JSON został wyeksportowany.")
        except (OSError, CustomTaskError, CustomTaskStorageError) as error:
            self._message(str(error), error=True)

    def _selected_set(self):
        return next(
            (item for item in self.sets if item.name == self.set_filter.get()),
            None,
        )

    def _message(self, text: str, *, error: bool = False) -> None:
        self.status.configure(
            text=text,
            text_color="#FCA5A5" if error else COLORS["success"],
        )
