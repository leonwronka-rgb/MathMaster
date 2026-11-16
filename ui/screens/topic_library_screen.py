from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from mathematics.library_service import (
    TopicLibraryError,
    TopicLibraryService,
    TopicLibraryStorageError,
)
from mathematics.topic_library import (
    LIBRARY_DIVISIONS,
    STATUS_LABELS,
    STATUS_VALUES,
    LibraryTopic,
)
from mathematics.topics import DIFFICULTY_LEVELS, DIFFICULTY_NAMES, TOPICS, Topic
from ui.theme import COLORS
from educational_content.service import ContentError, EducationalContentService


class TopicLibraryScreen(ctk.CTkFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        user_id: int,
        service: TopicLibraryService,
        on_practice: Callable[[LibraryTopic], None],
        content: EducationalContentService | None = None,
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self.user_id = user_id
        self.service = service
        self.on_practice = on_practice
        self.content = content
        self.selected_topic: LibraryTopic | None = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self,
            text="Biblioteka tematów",
            anchor="w",
            font=ctk.CTkFont(size=27, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", pady=(2, 12))

        filters = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=14)
        filters.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        filters.grid_columnconfigure(1, weight=1)
        self.search_entry = ctk.CTkEntry(
            filters, placeholder_text="Szukaj działu, tematu lub podtematu…"
        )
        self.search_entry.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=10)
        self.search_entry.bind("<KeyRelease>", self._refresh_results)
        self.division = ctk.CTkOptionMenu(
            filters,
            values=["Wszystkie działy", *(division.title for division in LIBRARY_DIVISIONS)],
            command=lambda _: self._refresh_results(),
        )
        self.division.grid(row=1, column=0, sticky="ew", padx=(12, 6), pady=(0, 10))
        self.difficulty = ctk.CTkOptionMenu(
            filters,
            values=["Wszystkie poziomy", *[str(level) for level in DIFFICULTY_LEVELS]],
            command=lambda _: self._refresh_results(),
        )
        self.difficulty.grid(row=1, column=1, sticky="ew", padx=6, pady=(0, 10))
        self.status_filter = ctk.CTkOptionMenu(
            filters,
            values=["Każdy status", *[STATUS_LABELS[value] for value in STATUS_VALUES]],
            command=lambda _: self._refresh_results(),
        )
        self.status_filter.grid(row=1, column=2, sticky="ew", padx=(6, 12), pady=(0, 10))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=2, uniform="library")
        body.grid_columnconfigure(1, weight=3, uniform="library")
        body.grid_rowconfigure(0, weight=1)
        self.results = ctk.CTkScrollableFrame(
            body, fg_color=COLORS["card"], corner_radius=14
        )
        self.results.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.detail = ctk.CTkScrollableFrame(
            body, fg_color=COLORS["card"], corner_radius=14
        )
        self.detail.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.add_button = ctk.CTkButton(
            self,
            text="＋ Dodaj temat",
            command=self._open_add_dialog,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        self.add_button.grid(row=3, column=0, sticky="e", pady=(12, 0))
        self._refresh_results()

    def _refresh_results(self, _event: object | None = None) -> None:
        for child in self.results.winfo_children():
            child.destroy()
        division = self.division.get()
        level = self.difficulty.get()
        status_label = self.status_filter.get()
        status = next(
            (key for key, label in STATUS_LABELS.items() if label == status_label),
            None,
        )
        try:
            topics = self.service.search(
                self.user_id,
                self.search_entry.get(),
                division=None if division == "Wszystkie działy" else division,
                difficulty=None if level == "Wszystkie poziomy" else int(level),
                status=status,
            )
            statuses = self.service.get_statuses(self.user_id)
        except (TopicLibraryError, TopicLibraryStorageError, ValueError) as error:
            self._show_message(str(error), error=True)
            return
        if not topics:
            self._show_message("Brak tematów spełniających wybrane filtry.")
            return
        for index, topic in enumerate(topics):
            current_status = STATUS_LABELS[statuses.get(topic.id, "unmastered")]
            ctk.CTkButton(
                self.results,
                text=f"{topic.division} › {topic.subdivision}\n{topic.title}\n"
                f"Poziom {topic.difficulty} · {current_status}"
                f"{' · własny' if topic.custom else ''}",
                anchor="w",
                height=64,
                fg_color=COLORS["surface"],
                hover_color=COLORS["card_hover"],
                command=lambda selected=topic: self._show_topic(selected),
            ).pack(fill="x", padx=8, pady=(8 if index == 0 else 3, 3))

    def _show_topic(self, topic: LibraryTopic) -> None:
        self.selected_topic = topic
        for child in self.detail.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self.detail,
            text=f"{topic.division} › {topic.subdivision}",
            anchor="w",
            text_color=COLORS["muted"],
        ).pack(fill="x", padx=14, pady=(14, 3))
        ctk.CTkLabel(
            self.detail,
            text=topic.title,
            anchor="w",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["text"],
        ).pack(fill="x", padx=14, pady=3)
        ctk.CTkLabel(
            self.detail,
            text=f"Poziom {topic.difficulty}: {DIFFICULTY_NAMES[topic.difficulty]}",
            anchor="w",
            text_color=COLORS["muted"],
        ).pack(fill="x", padx=14, pady=3)
        self._section("Opis", (topic.description,))
        material: dict[str, object] | None = None
        if self.content is not None:
            try:
                material = self.content.get_topic_material(topic.id)
            except ContentError:
                material = None
        if material is None:
            self._section("Teoria", topic.theory)
            self._section("Przykłady", topic.examples)
        else:
            self._section("Teoria", (str(material["theory"]),))
            for label, key in (
                ("Definicje", "definitions"),
                ("Wzory", "formulas"),
                ("Symbole", "symbols"),
                ("Przykłady krok po kroku", "worked_examples"),
                ("Typowe błędy", "common_errors"),
                ("Strategie rozwiązywania", "strategies"),
                ("Podsumowanie", "summary"),
            ):
                entries = material.get(key, [])
                if isinstance(entries, list):
                    self._section(label, tuple(str(item) for item in entries))
        self._section("Podtematy", topic.subtopics)

        ctk.CTkLabel(
            self.detail, text="Postęp", anchor="w",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=14, pady=(14, 5))
        status = ctk.CTkOptionMenu(
            self.detail,
            values=[STATUS_LABELS[value] for value in STATUS_VALUES],
            command=lambda label: self._set_status(topic, label),
        )
        current = self.service.get_statuses(self.user_id).get(topic.id, "unmastered")
        status.set(STATUS_LABELS[current])
        status.pack(fill="x", padx=14, pady=(0, 10))
        self._show_exercises(topic)
    def _section(self, title: str, items: tuple[str, ...]) -> None:
        ctk.CTkLabel(
            self.detail, text=title, anchor="w",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=14, pady=(12, 4))
        for item in items:
            ctk.CTkLabel(
                self.detail,
                text=f"• {item}",
                anchor="w",
                justify="left",
                wraplength=480,
                text_color=COLORS["muted"],
            ).pack(fill="x", padx=14, pady=2)

    def _set_status(self, topic: LibraryTopic, label: str) -> None:
        status = next(
            (key for key, value in STATUS_LABELS.items() if value == label), None
        )
        if status is None:
            self._show_message("Nieznany status tematu.", error=True)
            return
        try:
            self.service.set_status(self.user_id, topic.id, status)
        except (TopicLibraryError, TopicLibraryStorageError) as error:
            self._show_message(str(error), error=True)
            return
        self._refresh_results()

    def _show_exercises(self, topic: LibraryTopic) -> None:
        try:
            exercises = self.service.generate_exercises(self.user_id, topic.id)
        except (TopicLibraryError, TopicLibraryStorageError) as error:
            self._show_message(str(error), error=True)
            return
        self._section(
            "Przykład z rozwiązaniem",
            (f"{exercises[0].prompt}\n{exercises[0].solution}",),
        )
        self._section(
            "Ćwiczenia",
            tuple(exercise.prompt for exercise in exercises[1:]),
        )
        if self.content is not None:
            bank = self.content.list_tasks(topic_id=topic.id)
            if bank:
                counts = {
                    level: sum(item.difficulty == level for item in bank)
                    for level in DIFFICULTY_LEVELS
                }
                self._section(
                    "Zadania z biblioteki",
                    tuple(
                        f"{DIFFICULTY_NAMES[level]}: {count} zadań"
                        for level, count in counts.items() if count
                    ),
                )
        ctk.CTkButton(
            self.detail,
            text="Rozpocznij sesję z generatorem",
            command=lambda: self.on_practice(topic),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).pack(fill="x", padx=14, pady=(5, 14))

    def _open_add_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Dodaj temat do biblioteki")
        dialog.geometry("550x690")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            dialog,
            text="Nowy temat",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 8))
        fields: dict[str, ctk.CTkEntry] = {}
        prompts = (
            ("division", "Dział"),
            ("subdivision", "Poddział"),
            ("title", "Nazwa tematu"),
            ("description", "Opis"),
        )
        for row, (key, placeholder) in enumerate(prompts, start=1):
            entry = ctk.CTkEntry(dialog, placeholder_text=placeholder, height=38)
            entry.grid(row=row, column=0, sticky="ew", padx=20, pady=5)
            fields[key] = entry
        text_fields: dict[str, ctk.CTkTextbox] = {}
        for row, (key, title) in enumerate(
            (("theory", "Teoria (po jednej pozycji w wierszu)"),
             ("examples", "Przykłady (po jednej pozycji w wierszu)"),
             ("subtopics", "Podtematy (po jednej pozycji w wierszu)")),
            start=5,
        ):
            ctk.CTkLabel(dialog, text=title, anchor="w").grid(
                row=row, column=0, sticky="ew", padx=20, pady=(6, 0)
            )
            textbox = ctk.CTkTextbox(dialog, height=54)
            textbox.grid(row=row + 1, column=0, sticky="ew", padx=20, pady=(2, 5))
            text_fields[key] = textbox
        difficulty = ctk.CTkOptionMenu(
            dialog, values=[str(level) for level in DIFFICULTY_LEVELS]
        )
        difficulty.set("3")
        difficulty.grid(row=11, column=0, sticky="ew", padx=20, pady=6)
        generator_topic = ctk.CTkOptionMenu(
            dialog, values=[topic.value for topic in TOPICS]
        )
        generator_topic.set(Topic.ALGEBRA_EXPRESSION.value)
        generator_topic.grid(row=12, column=0, sticky="ew", padx=20, pady=6)
        feedback = ctk.CTkLabel(dialog, text="", text_color="#FCA5A5")
        feedback.grid(row=13, column=0, sticky="ew", padx=20, pady=4)

        def save_topic() -> None:
            try:
                self.service.add_topic(
                    self.user_id,
                    division=fields["division"].get(),
                    subdivision=fields["subdivision"].get(),
                    title=fields["title"].get(),
                    description=fields["description"].get(),
                    difficulty=int(difficulty.get()),
                    theory=self._textbox_lines(text_fields["theory"]),
                    examples=self._textbox_lines(text_fields["examples"]),
                    subtopics=self._textbox_lines(text_fields["subtopics"]),
                    exercise_topic=generator_topic.get(),
                )
            except (TopicLibraryError, TopicLibraryStorageError, ValueError) as error:
                feedback.configure(text=str(error))
                return
            dialog.destroy()
            self._refresh_results()

        ctk.CTkButton(
            dialog, text="Zapisz temat", command=save_topic,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        ).grid(row=14, column=0, sticky="ew", padx=20, pady=(8, 18))

    @staticmethod
    def _textbox_lines(textbox: ctk.CTkTextbox) -> tuple[str, ...]:
        return tuple(
            line.strip()
            for line in textbox.get("1.0", "end").splitlines()
            if line.strip()
        )

    def _show_message(self, text: str, *, error: bool = False) -> None:
        for child in self.detail.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self.detail,
            text=text,
            wraplength=460,
            justify="left",
            text_color="#FCA5A5" if error else COLORS["muted"],
        ).pack(fill="x", padx=16, pady=16)

