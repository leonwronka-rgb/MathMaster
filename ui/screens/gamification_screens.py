from __future__ import annotations

import customtkinter as ctk

from gamification.catalog import ACHIEVEMENTS
from gamification.service import GamificationService, RankingSort
from ui.theme import COLORS

_SORT_LABELS = {
    "XP": RankingSort.XP,
    "Poziom": RankingSort.LEVEL,
    "Zdane egzaminy": RankingSort.EXAMS,
}


class AchievementsScreen(ctk.CTkScrollableFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        gamification: GamificationService,
        user_id: int,
    ) -> None:
        super().__init__(
            parent,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.gamification = gamification
        self.user_id = user_id
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self, text="Poziom i osiągnięcia", anchor="w",
            font=ctk.CTkFont(size=27, weight="bold"), text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", pady=(5, 18))
        try:
            progress = gamification.get_level_progress(user_id)
        except RuntimeError as error:
            self._message(str(error), 1)
            return

        level_card = ctk.CTkFrame(
            self, fg_color=COLORS["card"], corner_radius=18,
            border_color=COLORS["border"], border_width=1,
        )
        level_card.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        level_card.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(level_card, fg_color="transparent")
        head.pack(fill="x", padx=19, pady=(17, 7))
        ctk.CTkLabel(
            head, text=f"Poziom {progress.level}",
            font=ctk.CTkFont(size=19, weight="bold"), text_color=COLORS["text"],
        ).pack(side="left")
        ctk.CTkLabel(
            head, text=f"{progress.xp} XP  ·  {progress.xp_to_next_level} XP do awansu",
            font=ctk.CTkFont(size=12), text_color="#C4B5FD",
        ).pack(side="right")
        bar = ctk.CTkProgressBar(
            level_card, height=10, corner_radius=8,
            fg_color=COLORS["border"], progress_color=COLORS["accent"],
        )
        bar.pack(fill="x", padx=19, pady=(3, 5))
        bar.set(progress.progress)
        ctk.CTkLabel(
            level_card,
            text=f"{progress.xp_in_level} / {progress.xp_for_next_level} XP na obecnym poziomie",
            anchor="w", font=ctk.CTkFont(size=11), text_color=COLORS["muted"],
        ).pack(fill="x", padx=19, pady=(0, 15))

        ctk.CTkLabel(
            self, text="Kolekcja osiągnięć", anchor="w",
            font=ctk.CTkFont(size=17, weight="bold"), text_color=COLORS["text"],
        ).grid(row=2, column=0, sticky="ew", pady=(0, 10))
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        categories = ["Wszystkie", *sorted({item.category for item in ACHIEVEMENTS})]
        rarities = ["Wszystkie", "Zwykłe", "Niezwykłe", "Rzadkie", "Epickie", "Legendarne"]
        self.category_filter = ctk.CTkOptionMenu(
            controls, values=categories, command=lambda _: self._load_gallery(),
            fg_color=COLORS["surface"], button_color=COLORS["accent"],
        )
        self.category_filter.set("Wszystkie")
        self.category_filter.pack(side="left", padx=(0, 6), expand=True, fill="x")
        self.rarity_filter = ctk.CTkOptionMenu(
            controls, values=rarities, command=lambda _: self._load_gallery(),
            fg_color=COLORS["surface"], button_color=COLORS["accent"],
        )
        self.rarity_filter.set("Wszystkie")
        self.rarity_filter.pack(side="left", padx=6, expand=True, fill="x")
        self.status_filter = ctk.CTkOptionMenu(
            controls, values=["Wszystkie", "Odblokowane", "Do zdobycia", "Historia"],
            command=lambda _: self._load_gallery(),
            fg_color=COLORS["surface"], button_color=COLORS["accent"],
        )
        self.status_filter.set("Wszystkie")
        self.status_filter.pack(side="left", padx=(6, 0), expand=True, fill="x")
        self.gallery = ctk.CTkScrollableFrame(
            self, fg_color="transparent", height=380,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.gallery.grid(row=4, column=0, sticky="nsew", pady=(0, 12))
        self.grid_rowconfigure(4, weight=1)
        self.cosmetic_status = ctk.CTkLabel(
            self, text="", anchor="w", text_color=COLORS["muted"]
        )
        self.cosmetic_status.grid(row=6, column=0, sticky="ew", pady=(4, 0))
        self.cosmetic_controls = ctk.CTkFrame(
            self, fg_color=COLORS["card"], corner_radius=14,
            border_color=COLORS["border"], border_width=1,
        )
        self.cosmetic_controls.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        self.cosmetic_controls.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(self.cosmetic_controls, text="Odznaka", text_color=COLORS["muted"]).grid(
            row=0, column=0, padx=(12, 4), pady=10
        )
        ctk.CTkLabel(self.cosmetic_controls, text="Ramka avatara", text_color=COLORS["muted"]).grid(
            row=0, column=2, padx=(12, 4), pady=10
        )
        self.badge_menu = ctk.CTkOptionMenu(
            self.cosmetic_controls, values=["Brak"], fg_color=COLORS["surface"],
            button_color=COLORS["accent"],
        )
        self.badge_menu.grid(row=0, column=1, sticky="ew", padx=4, pady=8)
        self.frame_menu = ctk.CTkOptionMenu(
            self.cosmetic_controls, values=["Brak"], fg_color=COLORS["surface"],
            button_color=COLORS["accent"],
        )
        self.frame_menu.grid(row=0, column=3, sticky="ew", padx=4, pady=8)
        ctk.CTkButton(
            self.cosmetic_controls, text="Zastosuj", width=90,
            command=self._equip_cosmetics, fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).grid(row=0, column=4, padx=10, pady=8)
        self._load_gallery()
        self._load_cosmetics()

    def _load_gallery(self) -> None:
        for child in self.gallery.winfo_children():
            child.destroy()
        try:
            category = self.category_filter.get()
            rarity = self.rarity_filter.get()
            achievements = self.gamification.get_achievements(
                self.user_id,
                category=None if category == "Wszystkie" else category,
                rarity=None if rarity == "Wszystkie" else rarity,
            )
        except RuntimeError as error:
            ctk.CTkLabel(
                self.gallery, text=f"Nie udało się wczytać osiągnięć: {error}",
                anchor="w", wraplength=650, text_color="#FCA5A5",
            ).pack(fill="x", padx=12, pady=12)
            return
        selected = self.status_filter.get()
        if selected in {"Odblokowane", "Historia"}:
            achievements = tuple(item for item in achievements if item.unlocked)
        elif selected == "Do zdobycia":
            achievements = tuple(item for item in achievements if not item.unlocked)
        if selected == "Historia":
            achievements = tuple(
                sorted(achievements, key=lambda item: item.unlocked_at or "", reverse=True)
            )
        if not achievements:
            ctk.CTkLabel(
                self.gallery, text="Brak osiągnięć dla wybranych filtrów.",
                text_color=COLORS["muted"],
            ).pack(padx=12, pady=18, anchor="w")
            return
        for achievement in achievements:
            card = ctk.CTkFrame(
                self.gallery,
                fg_color=COLORS["accent_soft"] if achievement.unlocked else COLORS["card"],
                corner_radius=14,
                border_color=COLORS["accent"] if achievement.unlocked else COLORS["border"],
                border_width=1,
            )
            card.pack(fill="x", pady=4)
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                card, text=achievement.icon if achievement.available else "🔒",
                width=40, font=ctk.CTkFont(size=22),
                text_color=COLORS["accent"] if achievement.unlocked else COLORS["muted"],
            ).grid(row=0, column=0, rowspan=2, padx=(14, 8), pady=12)
            ctk.CTkLabel(
                card, text=achievement.title, anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=COLORS["text"] if achievement.unlocked else COLORS["muted"],
            ).grid(row=0, column=1, sticky="ew", pady=(11, 0))
            ctk.CTkLabel(
                card,
                text=(
                    achievement.description
                    if achievement.available
                    else "Niedostępne bez zaufanego klucza serwera Quiz Battle."
                ),
                anchor="w",
                font=ctk.CTkFont(size=11), text_color=COLORS["muted"],
            ).grid(row=1, column=1, sticky="ew", pady=(2, 11))
            status = (
                f"Odblokowano {achievement.unlocked_at or ''} · +{achievement.xp_reward} XP"
                if achievement.unlocked
                else f"{achievement.category} · {achievement.rarity} · +{achievement.xp_reward} XP"
            )
            ctk.CTkLabel(
                card, text=status, font=ctk.CTkFont(size=10),
                text_color=COLORS["success"] if achievement.unlocked else COLORS["muted"],
            ).grid(row=0, column=2, padx=14, pady=(8, 0))
            if not achievement.unlocked:
                bar = ctk.CTkProgressBar(
                    card, height=6, progress_color=COLORS["accent"],
                    fg_color=COLORS["border"],
                )
                bar.grid(row=1, column=2, sticky="ew", padx=14, pady=(0, 4))
                bar.set(achievement.progress if achievement.available else 0)
                ctk.CTkLabel(
                    card, text=achievement.progress_text, font=ctk.CTkFont(size=9),
                    text_color=COLORS["muted"],
                ).grid(row=2, column=1, columnspan=2, sticky="w", padx=4, pady=(0, 8))

    def _load_cosmetics(self) -> None:
        try:
            cosmetics = self.gamification.get_cosmetics(self.user_id)
        except RuntimeError as error:
            self.cosmetic_status.configure(text=str(error))
            return
        badges = [key for kind, key, _ in cosmetics if kind == "badge"]
        frames = [key for kind, key, _ in cosmetics if kind == "avatar_frame"]
        self.badge_menu.configure(values=["Brak", *badges])
        self.frame_menu.configure(values=["Brak", *frames])
        self.badge_menu.set(next(
            (key for kind, key, equipped in cosmetics if kind == "badge" and equipped),
            "Brak",
        ))
        self.frame_menu.set(next(
            (key for kind, key, equipped in cosmetics if kind == "avatar_frame" and equipped),
            "Brak",
        ))

    def _equip_cosmetics(self) -> None:
        try:
            self.gamification.equip_cosmetic(
                self.user_id, "badge",
                None if self.badge_menu.get() == "Brak" else self.badge_menu.get(),
            )
            self.gamification.equip_cosmetic(
                self.user_id, "avatar_frame",
                None if self.frame_menu.get() == "Brak" else self.frame_menu.get(),
            )
            self.cosmetic_status.configure(text="Zapisano wygląd profilu.")
            self._load_cosmetics()
        except (RuntimeError, ValueError) as error:
            self.cosmetic_status.configure(text=str(error))

    def _message(self, text: str, row: int) -> None:
        ctk.CTkLabel(
            self, text=text, anchor="w", wraplength=650,
            text_color="#FCA5A5",
        ).grid(row=row, column=0, sticky="ew")


class RankingScreen(ctk.CTkFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        gamification: GamificationService,
        user_id: int,
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self.gamification = gamification
        self.user_id = user_id
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(4, 17))
        ctk.CTkLabel(
            header, text="Ranking lokalny", anchor="w",
            font=ctk.CTkFont(size=27, weight="bold"), text_color=COLORS["text"],
        ).pack(side="left")
        self.sort_menu = ctk.CTkOptionMenu(
            header,
            values=list(_SORT_LABELS),
            command=self._load_ranking,
            fg_color=COLORS["surface"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        self.sort_menu.set("XP")
        self.sort_menu.pack(side="right")
        self.place_label = ctk.CTkLabel(
            self, text="", anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#C4B5FD",
        )
        self.place_label.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.table = ctk.CTkScrollableFrame(
            self, fg_color=COLORS["card"], corner_radius=16,
            border_color=COLORS["border"], border_width=1,
        )
        self.table.grid(row=2, column=0, sticky="nsew")
        self._load_ranking("XP")

    def _load_ranking(self, selected: str) -> None:
        for child in self.table.winfo_children():
            child.destroy()
        try:
            entries = self.gamification.get_ranking(
                self.user_id, _SORT_LABELS[selected], limit=100
            )
        except (RuntimeError, ValueError) as error:
            self.place_label.configure(text=f"Nie udało się wczytać rankingu: {error}")
            return
        current = next((entry for entry in entries if entry.is_current_user), None)
        self.place_label.configure(
            text=(
                f"Twoje miejsce: #{current.place}"
                if current is not None
                else "Nie znaleziono Twojego konta w rankingu."
            )
        )
        header = ctk.CTkFrame(self.table, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(9, 4))
        for text, width in (
            ("Miejsce", 70), ("Użytkownik", 180), ("Poziom", 80),
            ("XP", 100), ("Zdane egzaminy", 130),
        ):
            ctk.CTkLabel(
                header, text=text, width=width, anchor="w",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=COLORS["muted"],
            ).pack(side="left", padx=4)
        if not entries:
            ctk.CTkLabel(
                self.table, text="Brak lokalnych kont w rankingu.",
                text_color=COLORS["muted"],
            ).pack(padx=18, pady=20)
            return
        for entry in entries:
            row = ctk.CTkFrame(
                self.table,
                fg_color=COLORS["accent_soft"] if entry.is_current_user else "transparent",
                corner_radius=10,
            )
            row.pack(fill="x", padx=8, pady=2)
            values = (
                f"#{entry.place}", entry.display_name,
                str(entry.level), f"{entry.xp} XP", str(entry.completed_exams),
            )
            for value, width in zip(values, (70, 180, 80, 100, 130)):
                ctk.CTkLabel(
                    row, text=value, width=width, anchor="w",
                    font=ctk.CTkFont(
                        size=12, weight="bold" if entry.is_current_user else "normal"
                    ),
                    text_color=COLORS["text"] if entry.is_current_user else COLORS["muted"],
                ).pack(side="left", padx=4, pady=8)
