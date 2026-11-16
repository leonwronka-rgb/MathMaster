from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox
from tkinter import font as tkfont
from typing import Any, Callable

import customtkinter as ctk

from accounts.auth import User
from mathematics.topics import DIFFICULTY_NAMES, TOPIC_CATEGORIES
from settings.backup_manager import BackupManager
from settings.settings_manager import (
    DEFAULT_SETTINGS,
    SettingsError,
    SettingsManager,
    SettingsStorageError,
)
from settings.theme_manager import ThemeManager
from ui.theme import COLORS

_CATEGORIES = (
    "Wygląd", "Personalizacja", "Nauka", "Powiadomienia",
    "Dźwięki i animacje", "Konto", "Dane i kopie zapasowe",
    "Informacje o aplikacji",
)
_DAYS = ("Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela")


class SettingsScreen(ctk.CTkFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        user: User,
        manager: SettingsManager,
        theme_manager: ThemeManager,
        backup_manager: BackupManager,
        profile_factory: Callable[[ctk.CTkFrame], ctk.CTkFrame],
        on_restore_complete: Callable[[], None],
        on_settings_changed: Callable[[dict[str, Any]], None],
        app_version: str,
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self.user = user
        self.manager = manager
        self.theme_manager = theme_manager
        self.backup_manager = backup_manager
        self.profile_factory = profile_factory
        self.on_restore_complete = on_restore_complete
        self.on_settings_changed = on_settings_changed
        self.app_version = app_version
        self.values = manager.get_settings(user.id)
        self.controls: dict[str, Any] = {}
        self.day_controls: list[ctk.CTkCheckBox] = []
        self.color_entries: dict[str, ctk.CTkEntry] = {}
        self.status: ctk.CTkLabel | None = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.menu = ctk.CTkFrame(self, width=190, corner_radius=16, fg_color=COLORS["card"])
        self.menu.grid(row=0, column=0, sticky="ns", padx=(0, 14), pady=(2, 52))
        self.menu.grid_propagate(False)
        self.menu.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.menu, text="USTAWIENIA", anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=COLORS["muted"],
        ).grid(row=0, column=0, sticky="ew", padx=13, pady=(16, 8))
        self.pages: dict[str, ctk.CTkScrollableFrame] = {}
        for index, category in enumerate(_CATEGORIES, 1):
            ctk.CTkButton(
                self.menu, text=category, anchor="w", height=36, corner_radius=9,
                fg_color="transparent", hover_color=COLORS["card_hover"],
                text_color=COLORS["text"],
                command=lambda selected=category: self.show_category(selected),
            ).grid(row=index, column=0, sticky="ew", padx=7, pady=2)

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        for category in _CATEGORIES:
            page = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_columnconfigure(0, weight=1)
            self.pages[category] = page
        self._active_category = _CATEGORIES[0]
        self._build_pages(profile_factory)
        self._load_controls()
        self.status = ctk.CTkLabel(self, text="", anchor="w", text_color=COLORS["muted"])
        self.status.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=0, columnspan=2, sticky="e", pady=(7, 0))
        ctk.CTkButton(
            actions, text="Anuluj", command=self.cancel,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions, text="Przywróć domyślne", command=self.reset,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions, text="Zapisz zmiany", command=self.save,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        ).pack(side="left", padx=(4, 0))
        self.show_category(_CATEGORIES[0])

    def _build_pages(self, profile_factory: Callable[[ctk.CTkFrame], ctk.CTkFrame]) -> None:
        self._heading("Wygląd", "Motyw i kolory aplikacji")
        self._option("theme", "Motyw aplikacji", ["Ciemny", "Jasny", "Systemowy", "Niestandardowy"], "Wygląd")
        self._heading("Personalizacja", "Czytelność i dostępność")
        self._option("font_size", "Rozmiar tekstu", ["Mały", "Normalny", "Duży", "Bardzo duży"], "Personalizacja")
        try:
            families = sorted(set(tkfont.families(self)), key=str.casefold)
        except tk.TclError:
            families = ["Segoe UI", "Arial", "TkDefaultFont"]
        if self.values.get("font_family") not in families:
            families.insert(0, self.values["font_family"])
        self._option("font_family", "Czcionka", families, "Personalizacja")
        self._switch("bold_text", "Pogrubiony tekst", "Personalizacja")
        self._option("spacing", "Odstępy interfejsu", ["Zwarte", "Normalne", "Przestronne"], "Personalizacja")
        self._switch("high_contrast", "Zwiększony kontrast", "Personalizacja")
        colors_page = self.pages["Personalizacja"]
        self.color_section = ctk.CTkFrame(colors_page, fg_color=COLORS["card"], corner_radius=14)
        self.color_section.grid(row=len(colors_page.winfo_children()), column=0, sticky="ew", padx=4, pady=8)
        ctk.CTkLabel(
            self.color_section, text="Kolory motywu niestandardowego", anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=14, pady=(12, 4))
        for key, label in (
            ("main", "Kolor główny"), ("secondary", "Kolor dodatkowy"),
            ("background", "Tło"), ("card", "Karty i panele"), ("text", "Tekst"),
            ("button", "Przyciski"), ("selection", "Zaznaczenie i aktywne elementy"),
        ):
            line = ctk.CTkFrame(self.color_section, fg_color="transparent")
            line.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(line, text=label, anchor="w").pack(side="left", expand=True, fill="x")
            entry = ctk.CTkEntry(line, width=110)
            entry.insert(0, self.values["custom_colors"][key])
            entry.pack(side="left", padx=(6, 4))
            ctk.CTkButton(
                line, text="Wybierz", width=70,
                command=lambda field=entry: self._choose_color(field),
            ).pack(side="left")
            self.color_entries[key] = entry

        self._option(
            "default_difficulty", "Domyślny poziom trudności",
            list(DIFFICULTY_NAMES.values()), "Nauka",
        )
        self._option("questions_per_session", "Zadania w sesji", ["5", "10", "15", "20", "30", "50", "100"], "Nauka")
        self._option("session_duration_minutes", "Czas sesji (minuty)", ["5", "15", "25", "45", "60", "90", "120"], "Nauka")
        self._switch("auto_next_question", "Automatyczne przejście po odpowiedzi", "Nauka")
        self._switch("show_hints", "Pokazuj podpowiedzi", "Nauka")
        self._switch("show_solution_after_error", "Pokazuj rozwiązanie po błędzie", "Nauka")
        self._switch("adaptive_difficulty", "Adaptacyjny poziom trudności", "Nauka")
        self._option("default_category", "Domyślny dział", list(TOPIC_CATEGORIES), "Nauka")

        self._switch("notifications_enabled", "Włącz powiadomienia", "Powiadomienia")
        self._switch("study_reminders", "Przypomnienia o nauce", "Powiadomienia")
        self._entry("reminder_time", "Godzina przypomnienia (HH:MM)", "Powiadomienia")
        self._switch("daily_goal_reminders", "Przypomnienie o dziennym celu", "Powiadomienia")
        self._switch("flashcard_reminders", "Przypomnienia o powtórkach fiszek", "Powiadomienia")
        days_frame = ctk.CTkFrame(self.pages["Powiadomienia"], fg_color=COLORS["card"], corner_radius=14)
        days_frame.grid(row=len(self.pages["Powiadomienia"].winfo_children()), column=0, sticky="ew", padx=4, pady=8)
        ctk.CTkLabel(days_frame, text="Dni przypomnień", anchor="w").pack(fill="x", padx=14, pady=(10, 4))
        for day, label in enumerate(_DAYS):
            check = ctk.CTkCheckBox(days_frame, text=label)
            check.pack(anchor="w", padx=14, pady=3)
            self.day_controls.append(check)

        self._switch("sound_enabled", "Efekty dźwiękowe przy odpowiedziach", "Dźwięki i animacje")
        volume = self._range("sound_volume", "Głośność efektów", 0, 100, "Dźwięki i animacje")
        self.volume_value = ctk.CTkLabel(
            self.pages["Dźwięki i animacje"], text="", anchor="w", text_color=COLORS["muted"]
        )
        self.volume_value.grid(
            row=len(self.pages["Dźwięki i animacje"].winfo_children()),
            column=0, sticky="ew", padx=12, pady=(0, 8),
        )
        volume.configure(command=self._volume_changed)
        self._switch("animations_enabled", "Animacje interfejsu", "Dźwięki i animacje")
        self._switch("reduce_animations", "Ogranicz animacje (wolniejszy komputer)", "Dźwięki i animacje")

        account_page = self.pages["Konto"]
        account_frame = profile_factory(account_page)
        account_frame.grid(row=0, column=0, sticky="nsew")
        account_page.grid_columnconfigure(0, weight=1)
        data_page = self.pages["Dane i kopie zapasowe"]
        self._heading("Dane i kopie zapasowe", "Eksport i przywracanie danych użytkownika")
        self._info(
            "Eksport JSON zawiera dane tego konta (bez skrótu hasła). Kopia SQLite obejmuje "
            "całą lokalną bazę, w tym wszystkie konta. Przywracanie tworzy automatyczną kopię "
            "bezpieczeństwa i wylogowuje użytkownika.",
            "Dane i kopie zapasowe",
        )
        self._button("Eksportuj moje dane do JSON", self._export_user_data, "Dane i kopie zapasowe")
        self._button("Utwórz kopię całej bazy SQLite", self._create_backup, "Dane i kopie zapasowe")
        self._button("Przywróć kopię bazy SQLite", self._restore_backup, "Dane i kopie zapasowe")
        self._heading("Informacje o aplikacji", "MathMaster")
        self._info(f"Wersja {self.app_version}\nDane użytkowników i historia nauki są przechowywane lokalnie w SQLite.", "Informacje o aplikacji")

    def _heading(self, title: str, subtitle: str, category: str | None = None) -> None:
        page = self.pages[category or title]
        ctk.CTkLabel(
            page, text=title, anchor="w", font=ctk.CTkFont(size=25, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
        ctk.CTkLabel(
            page, text=subtitle, anchor="w", text_color=COLORS["muted"],
        ).grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 14))

    def _option(self, key: str, label: str, values: list[str], category: str) -> None:
        line = self._row(category, label)
        control = ctk.CTkOptionMenu(line, values=values, width=230)
        value = self.values[key]
        if key == "default_difficulty":
            value = DIFFICULTY_NAMES[int(value)]
        elif key in {"questions_per_session", "session_duration_minutes"}:
            value = str(value)
        control.set(value)
        control.pack(side="right")
        self.controls[key] = control

    def _switch(self, key: str, label: str, category: str) -> None:
        line = self._row(category, label)
        control = ctk.CTkSwitch(line, text="")
        if self.values[key]:
            control.select()
        else:
            control.deselect()
        control.pack(side="right")
        self.controls[key] = control

    def _entry(self, key: str, label: str, category: str) -> None:
        line = self._row(category, label)
        control = ctk.CTkEntry(line, width=180)
        control.insert(0, str(self.values[key]))
        control.pack(side="right")
        self.controls[key] = control

    def _range(self, key: str, label: str, low: int, high: int, category: str) -> ctk.CTkSlider:
        line = self._row(category, label)
        control = ctk.CTkSlider(line, from_=low, to=high, number_of_steps=high-low, width=220)
        control.set(self.values[key])
        control.pack(side="right")
        self.controls[key] = control
        return control

    def _row(self, category: str, label: str) -> ctk.CTkFrame:
        page = self.pages[category]
        row = len(page.winfo_children())
        frame = ctk.CTkFrame(page, fg_color=COLORS["card"], corner_radius=12)
        frame.grid(row=row, column=0, sticky="ew", padx=4, pady=4)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=label, anchor="w", text_color=COLORS["text"]).pack(
            side="left", padx=13, pady=11, expand=True, fill="x"
        )
        return frame

    def _info(self, text: str, category: str) -> None:
        frame = self._row(category, text)
        frame.configure(fg_color=COLORS["surface"])
        frame.winfo_children()[0].configure(wraplength=700, justify="left")

    def _button(self, label: str, command: Callable[[], None], category: str) -> None:
        line = self._row(category, label)
        ctk.CTkButton(line, text=label, command=command).pack(side="right", padx=10, pady=7)

    @staticmethod
    def _choose_color(entry: ctk.CTkEntry) -> None:
        chosen = colorchooser.askcolor(entry.get(), title="Wybierz kolor")[1]
        if chosen:
            entry.delete(0, "end")
            entry.insert(0, chosen.upper())

    def _volume_changed(self, value: float) -> None:
        self.volume_value.configure(text=f"{round(value)}%")

    def show_category(self, category: str) -> None:
        for page in self.pages.values():
            page.grid_remove()
        self.pages[category].grid()
        self._active_category = category
        if category == "Personalizacja":
            if self.controls["theme"].get() == "Niestandardowy":
                self.color_section.grid()
            else:
                self.color_section.grid_remove()

    def _collect(self) -> dict[str, Any]:
        values = dict(self.values)
        values["custom_colors"] = dict(values["custom_colors"])
        for key, control in self.controls.items():
            if isinstance(control, ctk.CTkSwitch):
                values[key] = bool(control.get())
            elif isinstance(control, ctk.CTkSlider):
                values[key] = round(control.get())
            elif isinstance(control, ctk.CTkEntry):
                values[key] = control.get().strip()
            else:
                selected = control.get()
                if key == "default_difficulty":
                    values[key] = next(level for level, name in DIFFICULTY_NAMES.items() if name == selected)
                elif key in {"questions_per_session", "session_duration_minutes"}:
                    values[key] = int(selected)
                else:
                    values[key] = selected
        values["custom_colors"] = {
            key: entry.get().strip().upper() for key, entry in self.color_entries.items()
        }
        values["reminder_days"] = [
            day for day, control in enumerate(self.day_controls) if control.get()
        ]
        return values

    def save(self) -> None:
        try:
            self.values = self.manager.save_settings(self.user.id, self._collect())
            self.on_settings_changed(self.values)
            self.status.configure(text="Ustawienia zapisano i zastosowano.")
        except (SettingsError, SettingsStorageError) as error:
            self.status.configure(text=str(error), text_color=COLORS["error"])

    def cancel(self) -> None:
        try:
            self.values = self.manager.get_settings(self.user.id)
            self.on_settings_changed(self.values)
            self._load_controls()
            self.status.configure(text="Odrzucono niezapisane zmiany.")
        except SettingsStorageError as error:
            self.status.configure(text=str(error), text_color=COLORS["error"])

    def reset(self) -> None:
        if not messagebox.askyesno(
            "Przywróć domyślne", "Przywrócić domyślne ustawienia tego konta?"
        ):
            return
        try:
            self.values = self.manager.reset_settings(self.user.id)
            self.on_settings_changed(self.values)
            self._load_controls()
            self.status.configure(text="Przywrócono ustawienia domyślne.")
        except (SettingsError, SettingsStorageError) as error:
            self.status.configure(text=str(error), text_color=COLORS["error"])

    def _load_controls(self) -> None:
        for key, control in self.controls.items():
            value = self.values[key]
            if isinstance(control, ctk.CTkSwitch):
                control.select() if value else control.deselect()
            elif isinstance(control, ctk.CTkSlider):
                control.set(value)
            elif isinstance(control, ctk.CTkEntry):
                control.delete(0, "end")
                control.insert(0, str(value))
            elif key == "default_difficulty":
                control.set(DIFFICULTY_NAMES[int(value)])
            elif key in {"questions_per_session", "session_duration_minutes"}:
                control.set(str(value))
            else:
                control.set(value)
        for key, entry in self.color_entries.items():
            entry.delete(0, "end")
            entry.insert(0, self.values["custom_colors"][key])
        for day, control in enumerate(self.day_controls):
            control.select() if day in self.values["reminder_days"] else control.deselect()
        self.volume_value.configure(text=f"{self.values['sound_volume']}%")
        if self._active_category == "Personalizacja":
            self.show_category("Personalizacja")

    def _export_user_data(self) -> None:
        filename = filedialog.asksaveasfilename(
            title="Eksportuj moje dane",
            defaultextension=".json",
            filetypes=[("Plik JSON", "*.json")],
        )
        if not filename:
            return
        try:
            path = self.backup_manager.export_user_data(self.user.id, Path(filename))
            self.status.configure(text=f"Dane wyeksportowano: {path}")
        except (OSError, ValueError, RuntimeError) as error:
            self.status.configure(text=f"Nie udało się wyeksportować danych: {error}", text_color=COLORS["error"])

    def _create_backup(self) -> None:
        try:
            path = self.backup_manager.create_database_backup()
            self.status.configure(text=f"Kopia całej bazy utworzona: {path}")
        except (OSError, RuntimeError) as error:
            self.status.configure(text=f"Nie udało się utworzyć kopii: {error}", text_color=COLORS["error"])

    def _restore_backup(self) -> None:
        filename = filedialog.askopenfilename(
            title="Wybierz kopię SQLite",
            filetypes=[("Baza SQLite", "*.sqlite3 *.db"), ("Wszystkie pliki", "*.*")],
        )
        if not filename:
            return
        if not messagebox.askyesno(
            "Potwierdź przywracanie",
            "Przywrócenie zastąpi bieżącą bazę danych. Przedtem zostanie utworzona kopia bezpieczeństwa. Kontynuować?",
            icon="warning",
        ):
            return
        try:
            safety = self.backup_manager.restore_database_backup(Path(filename))
            self.status.configure(text=f"Kopia przywrócona. Kopia bezpieczeństwa: {safety}")
            self.on_restore_complete()
        except (OSError, ValueError, RuntimeError) as error:
            self.status.configure(text=f"Nie udało się przywrócić kopii: {error}", text_color=COLORS["error"])

