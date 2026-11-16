from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from config import AppConfig
from core.app import MathMasterApp


def main() -> None:
    config = AppConfig.from_environment()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=config.log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
    try:
        ctk.set_appearance_mode(config.appearance_mode)
        ctk.set_default_color_theme(config.color_theme)
        app = MathMasterApp(config)
        icon_path = config.icon_path
        if icon_path.is_file():
            app.iconbitmap(default=str(icon_path))
        else:
            logging.getLogger(__name__).warning("Application icon not found: %s", icon_path)
        app.mainloop()
    except Exception as error:
        logging.getLogger(__name__).exception("Application startup failed")
        try:
            messagebox.showerror(
                "MathMaster — błąd uruchamiania",
                f"Nie udało się uruchomić aplikacji:\n{error}",
            )
        except tk.TclError:
            pass
        raise


if __name__ == "__main__":
    main()
