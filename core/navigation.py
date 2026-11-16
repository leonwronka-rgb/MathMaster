from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from core.error_handler import ErrorHandler

ScreenFactory = Callable[[ctk.CTkFrame], ctk.CTkFrame]


class NavigationController:
    def __init__(self, container: ctk.CTkFrame, error_handler: ErrorHandler) -> None:
        self.container = container
        self.error_handler = error_handler
        self._screen_factories: dict[str, ScreenFactory] = {}
        self._current_screen: ctk.CTkFrame | None = None

    def register(self, name: str, factory: ScreenFactory) -> None:
        if not name.strip():
            raise ValueError("Nazwa ekranu nie może być pusta.")
        if name in self._screen_factories:
            raise ValueError(f"Ekran {name!r} jest już zarejestrowany.")
        self._screen_factories[name] = factory

    def navigate(self, name: str) -> None:
        try:
            factory = self._screen_factories[name]
        except KeyError as error:
            raise ValueError(f"Nie zarejestrowano ekranu {name!r}.") from error

        try:
            next_screen = factory(self.container)
            next_screen.pack(fill="both", expand=True)
        except Exception as error:
            self.error_handler.handle(error, f"Otwieranie ekranu {name}")
            return

        previous_screen = self._current_screen
        self._current_screen = next_screen
        if previous_screen is not None:
            previous_screen.destroy()