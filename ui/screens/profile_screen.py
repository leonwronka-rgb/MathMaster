from __future__ import annotations

from collections.abc import Callable
from tkinter import filedialog, messagebox

import customtkinter as ctk

from accounts.auth import AccountError, AuthService, User
from accounts.profile import ProfileService
from database.database import DatabaseBackupError
from gamification.service import GamificationService
from ui.theme import COLORS


class ProfileScreen(ctk.CTkFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        user: User,
        auth: AuthService,
        profiles: ProfileService,
        on_logout: Callable[[], None],
        on_delete: Callable[[], None],
        on_profile_updated: Callable[[str], None],
        on_create_backup: Callable[[], str] | None = None,
        on_restore_backup: Callable[[str], str] | None = None,
        gamification: GamificationService | None = None,
        on_username_updated: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self.user = user
        self.auth = auth
        self.profiles = profiles
        self.on_logout = on_logout
        self.on_delete = on_delete
        self.on_profile_updated = on_profile_updated
        self.on_username_updated = on_username_updated
        self.on_create_backup = on_create_backup
        self.on_restore_backup = on_restore_backup
        self._entry_widgets: list[ctk.CTkEntry] = []
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="Profil użytkownika", anchor="w",
            font=ctk.CTkFont(size=27, weight="bold"), text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", pady=(5, 20))
        try:
            profile = profiles.get_profile(user.id)
        except AccountError as error:
            self._message(str(error), error=True)
            return

        card = self._card(self, 1)
        ctk.CTkLabel(
            card, text="Dane konta", anchor="w",
            font=ctk.CTkFont(size=17, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=20, pady=(18, 8))
        ctk.CTkLabel(
            card, text=f"Użytkownik: @{profile.username}",
            anchor="w", text_color=COLORS["muted"],
        ).pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(
            card, text=f"Poziom {profile.level}   ·   {profile.xp} XP",
            anchor="w", text_color=COLORS["muted"],
        ).pack(fill="x", padx=20, pady=4)
        if gamification is not None:
            try:
                cosmetics = gamification.get_cosmetics(user.id)
            except RuntimeError as error:
                ctk.CTkLabel(
                    card, text=str(error), anchor="w", text_color="#FCA5A5",
                ).pack(fill="x", padx=20, pady=4)
                cosmetics = ()
            badge = next(
                (key for kind, key, equipped in cosmetics
                 if kind == "badge" and equipped),
                None,
            )
            frame = next(
                (key for kind, key, equipped in cosmetics
                 if kind == "avatar_frame" and equipped),
                None,
            )
            ctk.CTkLabel(
                card,
                text=f"Odznaka: {badge or 'brak'}   ·   Ramka: {frame or 'brak'}",
                anchor="w", text_color=COLORS["accent"],
            ).pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(
            card, text=f"Konto utworzone: {profile.created_at}",
            anchor="w", text_color=COLORS["muted"],
        ).pack(fill="x", padx=20, pady=(4, 16))

        edit = self._card(self, 2)
        ctk.CTkLabel(
            edit, text="Nazwa profilu", anchor="w",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=20, pady=(17, 7))
        self.name_entry = self._entry(edit, "Nazwa profilu")
        self.name_entry.insert(0, profile.display_name)
        self._button(edit, "Zapisz nazwę", self._save_name).pack(
            anchor="w", padx=20, pady=(0, 17)
        )
        self.username_entry = self._entry(edit, "Nazwa użytkownika")
        self.username_entry.insert(0, profile.username)
        self._button(edit, "Zmień nazwę użytkownika", self._save_username).pack(
            anchor="w", padx=20, pady=(0, 17)
        )

        change = self._card(self, 3)
        ctk.CTkLabel(
            change, text="Zmiana hasła", anchor="w",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=20, pady=(17, 7))
        self.current_password = self._entry(change, "Obecne hasło", show="•")
        self.new_password = self._entry(change, "Nowe hasło (min. 8 znaków)", show="•")
        self.confirm_password = self._entry(change, "Powtórz nowe hasło", show="•")
        self._button(change, "Zmień hasło", self._change_password).pack(
            anchor="w", padx=20, pady=(0, 12)
        )

        backup = self._card(self, 4)
        ctk.CTkLabel(
            backup, text="Kopia zapasowa danych", anchor="w",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=20, pady=(17, 7))
        ctk.CTkLabel(
            backup,
            text="Utwórz kopię lokalnej bazy lub przywróć dane z pliku.",
            anchor="w", text_color=COLORS["muted"],
        ).pack(fill="x", padx=20, pady=(0, 9))
        backup_actions = ctk.CTkFrame(backup, fg_color="transparent")
        backup_actions.pack(fill="x", padx=20, pady=(0, 15))
        self._button(
            backup_actions, "Utwórz kopię", self._create_backup
        ).pack(side="left", padx=(0, 8))
        self._button(
            backup_actions, "Przywróć z pliku", self._choose_backup,
            fg_color="#7F1D35", hover_color="#9F2444",
        ).pack(side="left")

        self.status = ctk.CTkLabel(
            self, text="", anchor="w", wraplength=560,
            font=ctk.CTkFont(size=12), text_color=COLORS["success"],
        )
        self.status.grid(row=5, column=0, sticky="ew", pady=9)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=6, column=0, sticky="ew", pady=(5, 20))
        self._button(actions, "Wyloguj się", on_logout).pack(side="left")
        self._button(
            actions, "Usuń konto…", self._confirm_delete,
            fg_color="#7F1D35", hover_color="#9F2444",
        ).pack(side="right")

    @staticmethod
    def _card(parent: ctk.CTkFrame, row: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent, fg_color=COLORS["card"], corner_radius=17,
            border_color=COLORS["border"], border_width=1,
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 13))
        return card

    def _entry(
        self, parent: ctk.CTkFrame, placeholder: str, show: str | None = None
    ) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(
            parent, height=39, corner_radius=10, placeholder_text=placeholder,
            show=show or "", fg_color=COLORS["background"],
            border_color=COLORS["border"], text_color=COLORS["text"],
        )
        entry.pack(fill="x", padx=20, pady=5)
        self._entry_widgets.append(entry)
        return entry

    @staticmethod
    def _button(
        parent: ctk.CTkFrame,
        text: str,
        command: Callable[[], None],
        fg_color: str = COLORS["accent"],
        hover_color: str = COLORS["accent_hover"],
    ) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent, text=text, command=command, height=37, corner_radius=11,
            fg_color=fg_color, hover_color=hover_color,
        )

    def _save_name(self) -> None:
        try:
            name = self.profiles.update_display_name(
                self.user.id, self.name_entry.get()
            )
            self.on_profile_updated(name)
            self._message("Nazwa profilu została zaktualizowana.")
        except (AccountError, ValueError) as error:
            self._message(str(error), error=True)

    def _save_username(self) -> None:
        try:
            username = self.profiles.update_username(
                self.user.id, self.username_entry.get()
            )
            self.auth.remember_account(username)
            self.username_entry.delete(0, "end")
            self.username_entry.insert(0, username)
            if self.on_username_updated is not None:
                self.on_username_updated(username)
            self._message("Nazwa użytkownika została zmieniona.")
        except (AccountError, ValueError) as error:
            self._message(str(error), error=True)

    def _change_password(self) -> None:
        if self.new_password.get() != self.confirm_password.get():
            self._message("Nowe hasła nie są takie same.", error=True)
            return
        try:
            self.auth.change_password(
                self.user.id, self.current_password.get(), self.new_password.get()
            )
            self.current_password.delete(0, "end")
            self.new_password.delete(0, "end")
            self.confirm_password.delete(0, "end")
            self._message("Hasło zostało zmienione.")
        except AccountError as error:
            self._message(str(error), error=True)

    def _confirm_delete(self) -> None:
        dialog = ctk.CTkInputDialog(
            text="Wpisz hasło, aby trwale usunąć konto i jego dane:",
            title="Usuwanie konta",
        )
        password = dialog.get_input()
        if password is None:
            return
        try:
            self.auth.delete_account(self.user.id, password)
            self.on_delete()
        except AccountError as error:
            self._message(str(error), error=True)

    def _create_backup(self) -> None:
        if self.on_create_backup is None:
            return
        try:
            backup_path = self.on_create_backup()
            self._message(f"Kopia zapisana: {backup_path}")
        except (DatabaseBackupError, OSError, RuntimeError) as error:
            self._message(str(error), error=True)

    def _choose_backup(self) -> None:
        if self.on_restore_backup is None:
            return
        backup_path = filedialog.askopenfilename(
            parent=self,
            title="Wybierz kopię zapasową",
            filetypes=(("Bazy SQLite", "*.sqlite3 *.db"), ("Wszystkie pliki", "*.*")),
        )
        if not backup_path:
            return
        if not messagebox.askyesno(
            "Przywrócić kopię?",
            "Bieżące dane zostaną zastąpione. Przed przywróceniem aplikacja "
            "utworzy kopię bezpieczeństwa. Kontynuować?",
            parent=self,
        ):
            return
        try:
            safety_path = self.on_restore_backup(backup_path)
            self._message(f"Przywrócono kopię. Kopia bieżących danych: {safety_path}")
            self.on_logout()
        except (DatabaseBackupError, FileNotFoundError, ValueError, RuntimeError) as error:
            self._message(str(error), error=True)

    def _message(self, text: str, error: bool = False) -> None:
        self.status.configure(
            text=text,
            text_color="#FCA5A5" if error else COLORS["success"],
        )
