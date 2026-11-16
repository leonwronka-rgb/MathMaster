from __future__ import annotations

import customtkinter as ctk

from assistant.assistant_service import (
    AssistantInputError,
    Explanation,
    MathAssistantService,
)
from ui.theme import COLORS


class MathAssistantScreen(ctk.CTkScrollableFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        service: MathAssistantService | None = None,
    ) -> None:
        super().__init__(
            parent,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.service = service or MathAssistantService()
        self.explanation: Explanation | None = None
        self.step_index = 0
        self.show_all_steps = False
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Asystent matematyczny",
            anchor="w",
            font=ctk.CTkFont(size=27, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", pady=(5, 6))
        ctk.CTkLabel(
            self,
            text="Wpisz zadanie, aby otrzymać zweryfikowane wyjaśnienie krok po kroku.",
            anchor="w",
            text_color=COLORS["muted"],
            wraplength=700,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 15))

        input_card = self._card(self, "Treść zadania")
        input_card.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        input_card.grid_columnconfigure(0, weight=1)
        self.problem_entry = ctk.CTkTextbox(
            input_card,
            height=82,
            wrap="word",
            fg_color=COLORS["surface"],
            text_color=COLORS["text"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=10,
        )
        self.problem_entry.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        self.problem_entry.insert("1.0", "2x + 6 = 14")
        ctk.CTkButton(
            input_card,
            text="Wyjaśnij zadanie",
            command=self._explain,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 15))

        self.status = ctk.CTkLabel(
            self,
            text="Obsługiwane są obecnie równania liniowe z jedną niewiadomą x.",
            anchor="w",
            justify="left",
            wraplength=740,
            text_color=COLORS["muted"],
        )
        self.status.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self.solution_card = self._card(self, "Rozwiązanie")
        self.solution_card.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        self.solution_card.grid_columnconfigure(0, weight=1)
        self.solution_card.grid_remove()
        self.step_heading = ctk.CTkLabel(
            self.solution_card,
            text="",
            anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text"],
        )
        self.step_heading.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))
        self.step_content = ctk.CTkFrame(
            self.solution_card, fg_color=COLORS["surface"], corner_radius=12
        )
        self.step_content.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.step_content.grid_columnconfigure(0, weight=1)
        self.controls = ctk.CTkFrame(self.solution_card, fg_color="transparent")
        self.controls.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        self.previous_button = ctk.CTkButton(
            self.controls,
            text="← Poprzedni krok",
            command=self._previous_step,
            fg_color=COLORS["surface"],
            hover_color=COLORS["card_hover"],
        )
        self.previous_button.pack(side="left")
        self.next_button = ctk.CTkButton(
            self.controls,
            text="Następny krok →",
            command=self._next_step,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        self.next_button.pack(side="left", padx=8)
        self.show_all_button = ctk.CTkButton(
            self.controls,
            text="Pokaż całe rozwiązanie",
            command=self._toggle_all_steps,
            fg_color=COLORS["surface"],
            hover_color=COLORS["card_hover"],
        )
        self.show_all_button.pack(side="right")

        self.mistakes_card = self._card(self, "Typowe błędy")
        self.mistakes_card.grid(row=5, column=0, sticky="ew", pady=(0, 20))
        self.mistakes_card.grid_columnconfigure(0, weight=1)
        self.mistakes_card.grid_remove()
        self._mistake_labels: list[ctk.CTkLabel] = []

    @staticmethod
    def _card(parent: ctk.CTkBaseClass, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["card"],
            corner_radius=18,
            border_color=COLORS["border"],
            border_width=1,
        )
        ctk.CTkLabel(
            card,
            text=title,
            anchor="w",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 10))
        return card

    def _explain(self) -> None:
        problem = self.problem_entry.get("1.0", "end-1c")
        self.explanation = None
        self.solution_card.grid_remove()
        self.mistakes_card.grid_remove()
        for label in self._mistake_labels:
            label.destroy()
        self._mistake_labels.clear()
        try:
            explanation = self.service.explain(problem)
        except AssistantInputError as error:
            self.status.configure(text=str(error), text_color="#FCA5A5")
            return
        self.explanation = explanation
        self.step_index = 0
        self.show_all_steps = False
        self.status.configure(
            text=(
                f"Rozpoznano: {explanation.task_type}. "
                f"Wynik: x = {explanation.answer}. "
                f"Sprawdzenie przez SymPy: "
                f"{'potwierdzone' if explanation.verified else 'niepotwierdzone'}."
            ),
            text_color=COLORS["success"] if explanation.verified else "#FCA5A5",
        )
        self.solution_card.grid()
        self.mistakes_card.grid()
        for index, mistake in enumerate(explanation.common_mistakes, start=1):
            label = ctk.CTkLabel(
                self.mistakes_card,
                text=f"{index}. {mistake}",
                anchor="w",
                justify="left",
                wraplength=740,
                text_color=COLORS["muted"],
            )
            label.grid(row=index, column=0, sticky="ew", padx=16, pady=(0, 7))
            self._mistake_labels.append(label)
        self._render_steps()

    def _render_steps(self) -> None:
        if self.explanation is None:
            return
        for child in self.step_content.winfo_children():
            child.destroy()
        if self.show_all_steps:
            steps = tuple(enumerate(self.explanation.steps, start=1))
            self.step_heading.configure(
                text=f"{self.explanation.task_type} · pełne rozwiązanie"
            )
        else:
            steps = ((self.step_index + 1, self.explanation.steps[self.step_index]),)
            self.step_heading.configure(
                text=(
                    f"{self.explanation.task_type} · krok "
                    f"{self.step_index + 1} z {len(self.explanation.steps)}"
                )
            )
        for row, (number, step) in enumerate(steps):
            panel = ctk.CTkFrame(self.step_content, fg_color="transparent")
            panel.grid(row=row, column=0, sticky="ew", padx=12, pady=(10, 4))
            panel.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                panel,
                text=f"{number}. {step.title}",
                anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=COLORS["accent"],
            ).grid(row=0, column=0, sticky="ew", pady=(0, 4))
            ctk.CTkLabel(
                panel,
                text=step.explanation,
                anchor="w",
                justify="left",
                wraplength=690,
                text_color=COLORS["text"],
            ).grid(row=1, column=0, sticky="ew")
            ctk.CTkLabel(
                panel,
                text=step.equation,
                anchor="w",
                font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
                text_color=COLORS["success"],
            ).grid(row=2, column=0, sticky="ew", pady=(7, 0))
        if self.show_all_steps:
            self.previous_button.configure(state="disabled")
            self.next_button.configure(state="disabled")
            self.show_all_button.configure(text="Pokaż kroki pojedynczo")
        else:
            self.previous_button.configure(
                state="normal" if self.step_index > 0 else "disabled"
            )
            self.next_button.configure(
                state="normal"
                if self.step_index + 1 < len(self.explanation.steps)
                else "disabled"
            )
            self.show_all_button.configure(text="Pokaż całe rozwiązanie")

    def _previous_step(self) -> None:
        if self.explanation is None or self.show_all_steps or self.step_index == 0:
            return
        self.step_index -= 1
        self._render_steps()

    def _next_step(self) -> None:
        if (
            self.explanation is None
            or self.show_all_steps
            or self.step_index + 1 >= len(self.explanation.steps)
        ):
            return
        self.step_index += 1
        self._render_steps()

    def _toggle_all_steps(self) -> None:
        if self.explanation is None:
            return
        self.show_all_steps = not self.show_all_steps
        self._render_steps()
