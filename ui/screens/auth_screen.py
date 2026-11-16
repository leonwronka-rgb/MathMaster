from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from accounts.auth import AccountError, AuthService, User
from ui.theme import COLORS


class AuthScreen(ctk.CTkFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        auth: AuthService,
        on_authenticated: Callable[[User], None],
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self.auth = auth
        self.on_authenticated = on_authenticated
        self.is_registering = False

        self.card = ctk.CTkFrame(
            self, fg_color=COLORS["card"], corner_radius=22,
            border_color=COLORS["border"], border_width=1,
        )
        self.card.place(relx=0.5, rely=0.48, anchor="center", relwidth=0.88)
        self.card.grid_columnconfigure(0, weight=1)
        self.mark = ctk.CTkLabel(
            self.card, text="∑", width=56, height=56, corner_radius=18,
            fg_color=COLORS["accent"], text_color="white",
            font=ctk.CTkFont(size=32, weight="bold"),
        )
        self.mark.grid(row=0, column=0, pady=(28, 12))
        self.title = ctk.CTkLabel(
            self.card, text="Witaj ponownie",
            font=ctk.CTkFont(size=24, weight="bold"), text_color=COLORS["text"],
        )
        self.title.grid(row=1, column=0, pady=(0, 5))
        self.subtitle = ctk.CTkLabel(
            self.card, text="Zaloguj się do swojego lokalnego konta",
            font=ctk.CTkFont(size=12), text_color=COLORS["muted"],
        )
        self.subtitle.grid(row=2, column=0, pady=(0, 18))

        self.form = ctk.CTkFrame(self.card, fg_color="transparent")
        self.form.grid(row=3, column=0, sticky="ew", padx=32)
        self.username = self._entry(self.form, "Nazwa użytkownika")
        try:
            remembered = self.auth.get_remembered_username()
        except AccountError as error:
            remembered = ""
            self._set_error(str(error))
        if remembered:
            self.username.insert(0, remembered)
        self.display_name = self._entry(self.form, "Nazwa profilu")
        self.password = self._entry(self.form, "Hasło", show="•")
        self.confirm = self._entry(self.form, "Powtórz hasło", show="•")
        self.remember = ctk.CTkCheckBox(
            self.form, text="Zapamiętaj konto i hasło na tym urządzeniu",
            font=ctk.CTkFont(size=11), text_color=COLORS["muted"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        )
        if remembered:
            try:
                remembered_password = self.auth.get_remembered_password()
            except AccountError as error:
                remembered_password = ""
                self._set_error(str(error))
            if remembered_password:
                self.password.insert(0, remembered_password)
                self.remember.select()
        self.remember.pack(anchor="w", pady=(1, 10))
        self.error_label = ctk.CTkLabel(
            self.card, text="", wraplength=380,
            font=ctk.CTkFont(size=12), text_color="#FCA5A5",
        )
        self.error_label.grid(row=4, column=0, padx=24, pady=(0, 5))
        self.submit = ctk.CTkButton(
            self.card, text="Zaloguj się", height=44, corner_radius=13,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._submit,
        )
        self.submit.grid(row=5, column=0, sticky="ew", padx=32, pady=(4, 12))
        self.switch = ctk.CTkButton(
            self.card, text="Nie masz konta? Utwórz je", height=34,
            fg_color="transparent", hover_color=COLORS["card_hover"],
            text_color="#C4B5FD", command=self._toggle_mode,
        )
        self.switch.grid(row=6, column=0, pady=(0, 22))
        self._refresh_fields()

    def _entry(
        self, parent: ctk.CTkFrame, placeholder: str, show: str | None = None
    ) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(
            parent,
            height=42,
            corner_radius=11,
            placeholder_text=placeholder,
            show=show or "",
            border_color=COLORS["border"],
            fg_color=COLORS["background"],
            text_color=COLORS["text"],
        )
        entry.pack(fill="x", pady=5)
        return entry

    def _toggle_mode(self) -> None:
        self.is_registering = not self.is_registering
        self.error_label.configure(text="")
        self._refresh_fields()

    def _refresh_fields(self) -> None:
        if self.is_registering:
            self.title.configure(text="Utwórz konto")
            self.subtitle.configure(text="Twoje postępy zostaną zapisane lokalnie")
            self.display_name.pack(fill="x", pady=5)
            self.confirm.pack(fill="x", pady=5)
            self.remember.pack_forget()
            self.submit.configure(text="Zarejestruj się")
            self.switch.configure(text="Masz już konto? Zaloguj się")
        else:
            self.title.configure(text="Witaj ponownie")
            self.subtitle.configure(text="Zaloguj się do swojego lokalnego konta")
            self.display_name.pack_forget()
            self.confirm.pack_forget()
            self.remember.pack(anchor="w", pady=(1, 10))
            self.submit.configure(text="Zaloguj się")
            self.switch.configure(text="Nie masz konta? Utwórz je")

    def _submit(self) -> None:
        self.error_label.configure(text="")
        username = self.username.get().strip()
        password = self.password.get()
        try:
            if self.is_registering:
                if password != self.confirm.get():
                    self._set_error("Podane hasła nie są takie same.")
                    return
                user = self.auth.register(
                    username, self.display_name.get(), password
                )
            else:
                user = self.auth.authenticate(username, password)
                self.auth.remember_account(
                    username if self.remember.get() else None,
                    password if self.remember.get() else None,
                )
            self.password.delete(0, "end")
            self.confirm.delete(0, "end")
            self.on_authenticated(user)
        except AccountError as error:
            self._set_error(str(error))

    def _set_error(self, message: str) -> None:
        self.error_label.configure(text=message)
