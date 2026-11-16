from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from ui.theme import COLORS


class NavigationSidebar(ctk.CTkFrame):
    ITEMS = (
        ("home", "Strona główna"),
        ("learning", "Nauka"),
        ("library", "Biblioteka"),
        ("exercises", "Ćwiczenia"),
        ("custom_tasks", "Moje zadania"),
        ("flashcards", "Fiszki"),
        ("exams", "Egzaminy"),
        ("quiz_battle", "Quiz Battle"),
        ("assistant", "Asystent"),
        ("achievements", "Osiągnięcia"),
        ("statistics", "Statystyki"),
        ("ranking", "Ranking"),
        ("plan", "Plan nauki"),
        ("settings", "Ustawienia"),
    )
    ICONS = {
        "home": "⌂",
        "learning": "◈",
        "library": "▤",
        "exercises": "✎",
        "custom_tasks": "✐",
        "flashcards": "▤",
        "exams": "▣",
        "quiz_battle": "⚔",
        "assistant": "✦",
        "achievements": "★",
        "statistics": "▥",
        "ranking": "♛",
        "plan": "▦",
        "settings": "⚙",
    }

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        app_name: str,
        on_navigate: Callable[[str], None],
    ) -> None:
        super().__init__(parent, width=248, corner_radius=0, fg_color=COLORS["surface"])
        self.grid_propagate(False)
        self._on_navigate = on_navigate
        self._active = "home"
        self._compact = False

        self.brand = ctk.CTkFrame(self, fg_color="transparent")
        self.brand.pack(fill="x", padx=22, pady=(27, 30))
        ctk.CTkLabel(
            self.brand,
            text="∑",
            width=42,
            height=42,
            corner_radius=14,
            fg_color=COLORS["accent"],
            text_color="white",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(side="left")
        self.brand_name = ctk.CTkLabel(
            self.brand,
            text=app_name,
            font=ctk.CTkFont(size=21, weight="bold"),
            text_color=COLORS["text"],
        )
        self.brand_name.pack(side="left", padx=12)

        self.nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.nav_frame.pack(fill="x", padx=12)
        self.buttons: dict[str, ctk.CTkButton] = {}
        self.labels = dict(self.ITEMS)
        for name, label in self.ITEMS:
            button = ctk.CTkButton(
                self.nav_frame,
                text=f"{self.ICONS[name]}   {label}",
                anchor="w",
                height=43,
                corner_radius=12,
                border_spacing=12,
                font=ctk.CTkFont(size=14, weight="bold" if name == "home" else "normal"),
                fg_color=COLORS["accent_soft"] if name == "home" else "transparent",
                hover_color=COLORS["card_hover"],
                text_color=COLORS["text"] if name == "home" else COLORS["muted"],
                command=lambda selected=name: self._select(selected),
            )
            button.pack(fill="x", pady=3)
            self.buttons[name] = button

        self.bottom = ctk.CTkFrame(self, fg_color="transparent")
        self.bottom.pack(side="bottom", fill="x", padx=16, pady=18)
        ctk.CTkFrame(self.bottom, height=1, fg_color=COLORS["border"]).pack(
            fill="x", pady=(0, 15)
        )
        self.profile = ctk.CTkFrame(
            self.bottom, fg_color=COLORS["card"], corner_radius=14
        )
        self.profile.pack(fill="x", ipady=5)
        ctk.CTkLabel(
            self.profile,
            text="U",
            width=34,
            height=34,
            corner_radius=12,
            fg_color=COLORS["accent_soft"],
            text_color="#C4B5FD",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left", padx=(9, 0), pady=8)
        self.profile_text = ctk.CTkFrame(self.profile, fg_color="transparent")
        self.profile_text.pack(side="left", padx=9)
        self.profile_name = ctk.CTkLabel(
            self.profile_text, text="Konto lokalne", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text"],
        )
        self.profile_name.pack(anchor="w")
        self.profile_username = ctk.CTkLabel(
            self.profile_text, text="", anchor="w",
            font=ctk.CTkFont(size=11), text_color=COLORS["muted"],
        )
        self.profile_username.pack(anchor="w", pady=(2, 0))

    def _select(self, name: str) -> None:
        self._active = name
        for item, button in self.buttons.items():
            active = item == name
            button.configure(
                fg_color=COLORS["accent_soft"] if active else "transparent",
                text_color=COLORS["text"] if active else COLORS["muted"],
            )
        self._on_navigate(name)

    def set_compact(self, compact: bool) -> None:
        if compact == self._compact:
            return
        self._compact = compact
        self.configure(width=76 if compact else 248)
        self.brand_name.pack_forget()
        if not compact:
            self.brand_name.pack(side="left", padx=12)
        self.bottom.pack_configure(padx=8 if compact else 16)
        self.profile_text.pack_forget()
        if not compact:
            self.profile_text.pack(side="left", padx=9)
        for name, button in self.buttons.items():
            button.configure(
                text=self.ICONS[name] if compact else f"{self.ICONS[name]}   {self.labels[name]}",
                anchor="center" if compact else "w",
                border_spacing=0 if compact else 12,
            )
        for child in self.profile.winfo_children():
            if child is not self.profile_text:
                child.pack_configure(padx=21 if compact else (9, 0))

    def set_user(self, display_name: str | None, username: str | None) -> None:
        self.profile_name.configure(text=display_name or "Konto lokalne")
        self.profile_username.configure(text=f"@{username}" if username else "Zaloguj się")

    def set_progress(self, level: int, xp: int) -> None:
        self.profile_username.configure(text=f"Poziom {level}  ·  {xp} XP")
