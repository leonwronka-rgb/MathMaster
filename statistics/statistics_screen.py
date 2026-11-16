from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from mathematics.topics import Topic
from statistics.service import (
    CategoryProgress,
    StatisticsService,
    StatisticsSnapshot,
    StatisticsStorageError,
)
from ui.theme import COLORS

_CHART_BG = COLORS["card"]
_CHART_GRID = COLORS["border"]


class StatisticsScreen(ctk.CTkScrollableFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        user_id: int,
        service: StatisticsService,
        on_practice: Callable[[Topic], None],
    ) -> None:
        super().__init__(
            parent,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.user_id = user_id
        self.service = service
        self.on_practice = on_practice
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(5, 15))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Statystyki nauki",
            anchor="w",
            font=ctk.CTkFont(size=27, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            header,
            text="Odśwież",
            width=100,
            command=self._refresh,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).grid(row=0, column=1, sticky="e")
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="ew")
        self.body.grid_columnconfigure(0, weight=1)
        self._refresh()

    def _refresh(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        loading = ctk.CTkLabel(
            self.body,
            text="Wczytywanie statystyk z historii nauki…",
            text_color=COLORS["muted"],
        )
        loading.grid(row=0, column=0, sticky="w", pady=15)
        self.update_idletasks()
        try:
            snapshot = self.service.get_statistics(self.user_id)
        except (StatisticsStorageError, ValueError) as error:
            loading.configure(
                text=f"Nie udało się wczytać statystyk: {error}",
                text_color="#FCA5A5",
            )
            return
        loading.destroy()
        self._render(snapshot)

    def _render(self, snapshot: StatisticsSnapshot) -> None:
        if snapshot.solved_tasks == 0:
            ctk.CTkLabel(
                self.body,
                text="Brak historii ćwiczeń. Rozwiąż zadania, aby zobaczyć swoje statystyki.",
                anchor="w",
                text_color=COLORS["muted"],
                wraplength=700,
            ).grid(row=0, column=0, sticky="ew", pady=(0, 15))
        self._render_metrics(snapshot)
        self._render_highlights(snapshot)
        self._render_charts(snapshot)
        self._render_topic_progress(snapshot)
        self._render_mistakes(snapshot)
        self._render_history(snapshot)

    def _card(self, row: int, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self.body,
            fg_color=COLORS["card"],
            corner_radius=16,
            border_color=COLORS["border"],
            border_width=1,
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(
            card,
            text=title,
            anchor="w",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=COLORS["text"],
        ).pack(fill="x", padx=16, pady=(14, 8))
        return card

    def _render_metrics(self, snapshot: StatisticsSnapshot) -> None:
        metrics = ctk.CTkFrame(self.body, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        for column in range(4):
            metrics.grid_columnconfigure(column, weight=1, uniform="stats")
        values = (
            ("Rozwiązane", str(snapshot.solved_tasks)),
            ("Poprawne", str(snapshot.correct_answers)),
            ("Skuteczność", f"{snapshot.accuracy_percent:.1f}%"),
            ("Czas nauki", self._format_duration(snapshot.study_seconds)),
        )
        for column, (label, value) in enumerate(values):
            card = ctk.CTkFrame(
                metrics,
                fg_color=COLORS["card"],
                corner_radius=15,
                border_color=COLORS["border"],
                border_width=1,
            )
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0))
            ctk.CTkLabel(
                card, text=label, text_color=COLORS["muted"],
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", padx=12, pady=(12, 3))
            ctk.CTkLabel(
                card, text=value, text_color=COLORS["text"],
                font=ctk.CTkFont(size=20, weight="bold"),
            ).pack(anchor="w", padx=12, pady=(0, 12))

    def _render_highlights(self, snapshot: StatisticsSnapshot) -> None:
        card = self._card(2, "Kategorie")
        columns = ctk.CTkFrame(card, fg_color="transparent")
        columns.pack(fill="x", padx=15, pady=(0, 14))
        columns.grid_columnconfigure((0, 1), weight=1)
        self._category_highlight(
            columns, "Najlepsze", snapshot.best_categories, 0, reverse=True
        )
        self._category_highlight(
            columns, "Wymagające najwięcej pracy", snapshot.hardest_categories, 1
        )

    @staticmethod
    def _category_highlight(
        parent: ctk.CTkFrame,
        title: str,
        categories: tuple[CategoryProgress, ...],
        column: int,
        reverse: bool = False,
    ) -> None:
        panel = ctk.CTkFrame(parent, fg_color="transparent")
        panel.grid(row=0, column=column, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(
            panel, text=title, anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["accent"] if reverse else COLORS["orange"],
        ).pack(anchor="w", pady=(0, 5))
        if not categories:
            ctk.CTkLabel(
                panel, text="Za mało danych", anchor="w",
                text_color=COLORS["muted"],
            ).pack(anchor="w")
            return
        for item in categories:
            ctk.CTkLabel(
                panel,
                text=f"{item.category}  ·  {item.accuracy_percent:.1f}% ({item.attempts})",
                anchor="w",
                text_color=COLORS["text"],
            ).pack(anchor="w", pady=2)

    def _render_charts(self, snapshot: StatisticsSnapshot) -> None:
        card = self._card(3, "Postęp i skuteczność")
        figure = Figure(figsize=(11.5, 7.2), dpi=90, facecolor=_CHART_BG)
        axes = figure.subplots(3, 2)
        figure.subplots_adjust(
            left=0.12, right=0.97, top=0.94, bottom=0.09, hspace=0.55, wspace=0.35
        )
        for axis in axes.flat:
            axis.set_facecolor(_CHART_BG)
            axis.tick_params(colors=COLORS["muted"], labelsize=8)
            axis.title.set_color(COLORS["text"])
            for spine in axis.spines.values():
                spine.set_color(_CHART_GRID)
            axis.grid(axis="y", color=_CHART_GRID, alpha=0.55, linewidth=0.6)
            axis.set_axisbelow(True)

        self._bar_chart(
            axes[0, 0],
            [label[5:] for label, _ in snapshot.daily_progress],
            [count for _, count in snapshot.daily_progress],
            "Rozwiązane zadania — ostatnie 14 dni",
        )
        self._bar_chart(
            axes[0, 1],
            [label[5:] for label, _ in snapshot.weekly_progress],
            [count for _, count in snapshot.weekly_progress],
            "Rozwiązane zadania — ostatnie 12 tygodni",
        )
        categories = snapshot.category_progress
        self._horizontal_chart(
            axes[1, 0],
            [item.category for item in categories],
            [item.accuracy_percent for item in categories],
            "Skuteczność według kategorii",
            "%",
            COLORS["accent"],
            xlim=(0, 100),
        )
        self._horizontal_chart(
            axes[1, 1],
            [item.category for item in categories],
            [item.attempts for item in categories],
            "Liczba rozwiązanych zadań",
            "zadań",
            COLORS["blue"],
        )
        difficulty_axis = axes[2, 0]
        difficulty_axis.set_title("Zmiana poziomu trudności", loc="left")
        difficulty = snapshot.difficulty_history
        if difficulty:
            difficulty_axis.step(
                range(1, len(difficulty) + 1),
                [item.difficulty for item in difficulty],
                where="mid",
                color=COLORS["accent"],
                linewidth=2,
            )
            difficulty_axis.set_ylim(0.5, 5.5)
            difficulty_axis.set_yticks(range(1, 6))
            difficulty_axis.set_ylabel("Poziom", color=COLORS["muted"], fontsize=8)
            difficulty_axis.set_xlabel("Zadanie w historii", color=COLORS["muted"], fontsize=8)
        else:
            self._empty_axis(difficulty_axis)
        axes[2, 1].axis("off")
        axes[2, 1].text(
            0.02, 0.95,
            "Czas nauki to suma czasu zapisanego przy sprawdzonych zadaniach.",
            color=COLORS["muted"],
            fontsize=9,
            va="top",
            wrap=True,
        )

        canvas = FigureCanvasTkAgg(figure, master=card)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(0, 10))
        self._figure_canvas = canvas

    @staticmethod
    def _empty_axis(axis: Axes) -> None:
        axis.text(
            0.5, 0.5, "Brak danych",
            transform=axis.transAxes,
            color=COLORS["muted"],
            ha="center",
            va="center",
            fontsize=9,
        )
        axis.set_xticks([])
        axis.set_yticks([])

    @classmethod
    def _bar_chart(
        cls, axis: Axes, labels: list[str], values: list[int], title: str
    ) -> None:
        axis.set_title(title, loc="left")
        if not values or not any(values):
            cls._empty_axis(axis)
            return
        axis.bar(range(len(values)), values, color=COLORS["accent"], width=0.72)
        stride = max(1, len(labels) // 7)
        axis.set_xticks(range(0, len(labels), stride))
        axis.set_xticklabels(labels[::stride], rotation=35, ha="right")
        axis.set_ylabel("Zadania", color=COLORS["muted"], fontsize=8)

    @classmethod
    def _horizontal_chart(
        cls,
        axis: Axes,
        labels: list[str],
        values: list[int] | list[float],
        title: str,
        unit: str,
        color: str,
        xlim: tuple[int, int] | None = None,
    ) -> None:
        axis.set_title(title, loc="left")
        if not values:
            cls._empty_axis(axis)
            return
        positions = range(len(labels))
        axis.barh(list(positions), values, color=color, height=0.64)
        axis.set_yticks(list(positions))
        axis.set_yticklabels(labels, fontsize=8)
        axis.invert_yaxis()
        axis.set_xlabel(unit, color=COLORS["muted"], fontsize=8)
        if xlim is not None:
            axis.set_xlim(*xlim)

    def _render_topic_progress(self, snapshot: StatisticsSnapshot) -> None:
        card = self._card(4, "Postęp w tematach")
        if not snapshot.topic_progress:
            self._empty_message(card, "Postęp pojawi się po rozwiązaniu pierwszych zadań.")
            return
        for item in snapshot.topic_progress:
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.pack(fill="x", padx=15, pady=(0, 7))
            line.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                line,
                text=f"{item.topic_label}  ·  {item.category}",
                anchor="w",
                text_color=COLORS["text"],
            ).grid(row=0, column=0, sticky="ew")
            ctk.CTkLabel(
                line,
                text=f"{item.correct}/{item.attempts}  ·  {item.accuracy_percent:.1f}%",
                text_color=COLORS["muted"],
            ).grid(row=0, column=1, sticky="e", padx=(10, 0))
            bar = ctk.CTkProgressBar(
                line,
                height=7,
                fg_color=COLORS["border"],
                progress_color=COLORS["accent"],
            )
            bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
            bar.set(item.accuracy_percent / 100)

    def _render_mistakes(self, snapshot: StatisticsSnapshot) -> None:
        card = self._card(5, "Analiza błędów i propozycje ćwiczeń")
        if not snapshot.mistakes:
            self._empty_message(card, "Nie zapisano błędnych odpowiedzi. Oby tak dalej!")
            return
        repeated = [item for item in snapshot.mistakes if item.repeated]
        if repeated:
            ctk.CTkLabel(
                card,
                text="Powtarzające się błędy — tematy z co najmniej dwiema błędnymi odpowiedziami:",
                anchor="w",
                wraplength=780,
                text_color=COLORS["orange"],
            ).pack(fill="x", padx=15, pady=(0, 7))
        for item in snapshot.mistakes:
            repeated_label = "  ·  powtarzający się błąd" if item.repeated else ""
            ctk.CTkLabel(
                card,
                text=(
                    f"{item.category} / {item.topic_label}: {item.incorrect} błędów "
                    f"w {item.attempts} zadaniach{repeated_label}. "
                    f"Ostatnia błędna odpowiedź: {item.latest_mistake or '—'}"
                ),
                anchor="w",
                wraplength=780,
                text_color=COLORS["text"],
            ).pack(fill="x", padx=15, pady=3)
        ctk.CTkLabel(
            card,
            text="Warto poćwiczyć:",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["accent"],
        ).pack(fill="x", padx=15, pady=(11, 5))
        for item in snapshot.recommendations:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=(0, 7))
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                row,
                text=f"{item.topic_label}  ·  skuteczność {item.accuracy_percent:.1f}%",
                anchor="w",
                text_color=COLORS["text"],
            ).grid(row=0, column=0, sticky="ew")
            ctk.CTkButton(
                row,
                text="Ćwicz temat",
                width=110,
                height=30,
                command=lambda topic=item.topic: self.on_practice(Topic(topic)),
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
            ).grid(row=0, column=1, sticky="e")

    def _render_history(self, snapshot: StatisticsSnapshot) -> None:
        card = self._card(6, "Historia wyników")
        if not snapshot.history:
            self._empty_message(card, "Historia jest pusta.")
            return
        for item in snapshot.history:
            correct_color = COLORS["success"] if item.correct else "#FCA5A5"
            status = "Poprawnie" if item.correct else "Błąd"
            ctk.CTkLabel(
                card,
                text=(
                    f"{item.completed_at[:16]}  ·  {item.topic_label}  ·  "
                    f"poziom {item.difficulty}  ·  {status}\n"
                    f"{item.question[:150]}\n"
                    f"Twoja odpowiedź: {item.submitted_answer[:80]}  ·  "
                    f"Poprawna: {item.correct_answer[:80]}"
                ),
                anchor="w",
                justify="left",
                wraplength=780,
                text_color=correct_color,
            ).pack(fill="x", padx=15, pady=(0, 9))
            ctk.CTkFrame(card, height=1, fg_color=COLORS["border"]).pack(
                fill="x", padx=15, pady=(0, 8)
            )

    @staticmethod
    def _empty_message(parent: ctk.CTkFrame, message: str) -> None:
        ctk.CTkLabel(
            parent, text=message, anchor="w", text_color=COLORS["muted"]
        ).pack(fill="x", padx=15, pady=(0, 14))

    @staticmethod
    def _format_duration(seconds: int) -> str:
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        if hours:
            return f"{hours} godz. {minutes} min"
        return f"{minutes} min"
