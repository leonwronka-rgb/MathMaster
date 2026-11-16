from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox


class ErrorHandler:
    def __init__(self, parent: tk.Misc) -> None:
        self.parent = parent
        self.logger = logging.getLogger("mathmaster.errors")

    def handle(self, error: Exception, context: str) -> None:
        self.logger.error(
            "%s: %s",
            context,
            error,
            exc_info=(type(error), error, error.__traceback__),
        )
        try:
            messagebox.showerror(
                "MathMaster — wystąpił błąd",
                f"{context}.\n\nSzczegóły: {error}",
                parent=self.parent,
            )
        except tk.TclError:
            self.logger.warning("Nie można wyświetlić okna błędu.")
