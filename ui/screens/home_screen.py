from __future__ import annotations

import customtkinter as ctk
from collections.abc import Callable

from config import AppConfig
from accounts.auth import User
from accounts.profile import ProfileService
from ui.components import create_page_title
from ui.theme import COLORS


class HomeScreen(ctk.CTkScrollableFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        config: AppConfig,
        on_navigate: Callable[[str], None],
        user: User,
        profiles: ProfileService,
    ) -> None:
        super().__init__(
            parent,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.grid_columnconfigure((0, 1, 2), weight=1, uniform="dashboard")
        self.grid_rowconfigure(3, weight=1)
        profile = profiles.get_profile(user.id)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 20))
        heading = ctk.CTkFrame(header, fg_color="transparent")
        heading.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            heading,
            text="TWÓJ PLAN NA DZIŚ",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLORS["accent"],
            anchor="w",
        ).pack(anchor="w", pady=(3, 5))
        ctk.CTkLabel(
            heading,
            text=f"Cześć, {user.display_name} 👋",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="✧   Matematyka, krok po kroku",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
        ).pack(side="right", padx=(8, 0), pady=(25, 0))

        ctk.CTkButton(
            header,
            text="▶  Rozpocznij naukę",
            height=40,
            corner_radius=12,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: on_navigate("learning"),
        ).pack(side="right", padx=(12, 0), pady=(16, 0))

        self._card(self, 1, 0, "✦", "Twój poziom", f"Poziom {profile.level}", "Początkujący", COLORS["accent"])
        self._card(self, 1, 1, "↗", "Punkty doświadczenia", f"{profile.xp} XP", "Każde zadanie się liczy", COLORS["blue"])
        self._card(self, 1, 2, "◷", "Seria nauki", "Zacznij dziś", "Buduj regularny nawyk", COLORS["orange"])

        progress = ctk.CTkFrame(
            self, fg_color=COLORS["card"], corner_radius=18,
            border_color=COLORS["border"], border_width=1,
        )
        progress.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(16, 20))
        progress.grid_columnconfigure(0, weight=1)
        progress_head = ctk.CTkFrame(progress, fg_color="transparent")
        progress_head.pack(fill="x", padx=20, pady=(17, 7))
        ctk.CTkLabel(
            progress_head, text="Dzisiejszy postęp",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=COLORS["text"],
        ).pack(side="left")
        ctk.CTkLabel(
            progress_head, text="0 / 20 min", font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
        ).pack(side="right")
        bar = ctk.CTkProgressBar(
            progress, height=9, corner_radius=8, fg_color=COLORS["border"],
            progress_color=COLORS["accent"],
        )
        bar.pack(fill="x", padx=20, pady=(1, 6))
        bar.set(0)
        ctk.CTkLabel(
            progress, text="Wykonaj pierwsze ćwiczenie, aby rozpocząć swój dzienny cel.",
            anchor="w", font=ctk.CTkFont(size=11), text_color=COLORS["muted"],
        ).pack(fill="x", padx=20, pady=(0, 15))

        self._section(self, 3, 0, "Ostatnie ćwiczenia", "Zobacz wszystko")
        self._empty_card(
            self, 4, 0, "◌", "Tu pojawią się Twoje ćwiczenia",
            "Rozwiązane zadania znajdziesz w tym miejscu.",
        )
        self._section(self, 3, 1, "Polecane tematy", "Odkrywaj")
        self._topic_card(self, 4, 1, "∑", "Arytmetyka", "Liczby i działania", COLORS["accent"], lambda: on_navigate("learning"))
        self._topic_card(self, 5, 1, "x²", "Algebra", "Wyrażenia i równania", COLORS["blue"], lambda: on_navigate("learning"))
        self._section(self, 3, 2, "Osiągnięcia", "Twoja kolekcja")
        self._empty_card(
            self, 4, 2, "♧", "Pierwsze osiągnięcie czeka",
            "Ćwicz regularnie, aby odblokować odznaki.",
        )
        self.grid_rowconfigure(5, weight=1)

    @staticmethod
    def _card(
        parent: ctk.CTkFrame,
        row: int,
        column: int,
        icon: str,
        title: str,
        value: str,
        caption: str,
        color: str,
    ) -> None:
        card = ctk.CTkFrame(
            parent, fg_color=COLORS["card"], corner_radius=18,
            border_color=COLORS["border"], border_width=1,
        )
        card.grid(row=row, column=column, sticky="nsew", padx=(0, 12) if column < 2 else (0, 0))
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            card, text=icon, width=38, height=38, corner_radius=12,
            fg_color=COLORS["accent_soft"], text_color=color,
            font=ctk.CTkFont(size=19, weight="bold"),
        ).grid(row=0, column=0, rowspan=2, padx=(15, 11), pady=15, sticky="n")
        ctk.CTkLabel(
            card, text=title, anchor="w", font=ctk.CTkFont(size=11),
            text_color=COLORS["muted"],
        ).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(15, 0))
        ctk.CTkLabel(
            card, text=value, anchor="w", font=ctk.CTkFont(size=21, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(1, 0))
        ctk.CTkLabel(
            card, text=caption, anchor="w", font=ctk.CTkFont(size=10),
            text_color=COLORS["muted"],
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 15))

    @staticmethod
    def _section(
        parent: ctk.CTkFrame, row: int, column: int, title: str, action: str
    ) -> None:
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.grid(row=row, column=column, sticky="ew", padx=(0, 12) if column < 2 else 0, pady=(0, 9))
        section.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            section, text=title, anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            section, text=action, anchor="e",
            font=ctk.CTkFont(size=10), text_color="#B9A2FF",
        ).grid(row=0, column=1, sticky="e")

    @staticmethod
    def _empty_card(
        parent: ctk.CTkFrame,
        row: int,
        column: int,
        icon: str,
        title: str,
        description: str,
    ) -> None:
        card = ctk.CTkFrame(
            parent, fg_color=COLORS["card"], corner_radius=16,
            border_color=COLORS["border"], border_width=1,
        )
        card.grid(row=row, column=column, rowspan=2, sticky="nsew", padx=(0, 12) if column < 2 else 0)
        ctk.CTkLabel(
            card, text=icon, font=ctk.CTkFont(size=28), text_color=COLORS["muted"],
        ).pack(anchor="w", padx=15, pady=(18, 8))
        ctk.CTkLabel(
            card, text=title, anchor="w", wraplength=230,
            font=ctk.CTkFont(size=12, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=15)
        ctk.CTkLabel(
            card, text=description, anchor="w", justify="left", wraplength=230,
            font=ctk.CTkFont(size=10), text_color=COLORS["muted"],
        ).pack(fill="x", padx=15, pady=(5, 16))

    @staticmethod
    def _topic_card(
        parent: ctk.CTkFrame, row: int, column: int,
        icon: str, title: str, subtitle: str, color: str,
        command: Callable[[], None],
    ) -> None:
        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["card"],
            corner_radius=14,
            border_color=COLORS["border"],
            border_width=1,
            cursor="hand2",
        )
        card.grid(row=row, column=column, sticky="ew", padx=(0, 12) if column < 2 else 0, pady=(0, 8))
        ctk.CTkLabel(
            card, text=icon, width=34, height=34, corner_radius=11,
            fg_color=COLORS["accent_soft"], text_color=color,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(side="left", padx=11, pady=10)
        text = ctk.CTkFrame(card, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True, pady=8)
        ctk.CTkLabel(
            text, text=title, anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=COLORS["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            text, text=subtitle, anchor="w",
            font=ctk.CTkFont(size=9), text_color=COLORS["muted"],
        ).pack(anchor="w", pady=(2, 0))
        for widget in (card, *card.winfo_children(), *text.winfo_children()):
            widget.bind("<Button-1>", lambda _event: command())
            widget.bind(
                "<Enter>",
                lambda _event, frame=card: frame.configure(
                    fg_color=COLORS["card_hover"]
                ),
            )
            widget.bind(
                "<Leave>",
                lambda _event, frame=card: frame.configure(
                    fg_color=COLORS["card"]
                ),
            )
