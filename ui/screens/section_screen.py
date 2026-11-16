from __future__ import annotations

import customtkinter as ctk

from ui.components import create_page_title
from ui.theme import COLORS


class SectionScreen(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, title: str) -> None:
        super().__init__(parent, fg_color="transparent")
        create_page_title(self, title)
        card = ctk.CTkFrame(
            self,
            fg_color=COLORS["card"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=20,
        )
        card.pack(fill="both", expand=True, pady=(8, 0))
        ctk.CTkLabel(
            card,
            text="✦",
            font=ctk.CTkFont(size=34),
            text_color=COLORS["accent"],
        ).pack(pady=(90, 12))
        ctk.CTkLabel(
            card,
            text=f"{title} — Twoja przestrzeń do nauki",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color=COLORS["text"],
        ).pack(pady=5)
        ctk.CTkLabel(
            card,
            text="Nie ma jeszcze danych w tej sekcji. Wróć tu po dodaniu materiałów.",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
            wraplength=480,
        ).pack(padx=24, pady=(4, 18))
