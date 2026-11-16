from __future__ import annotations

import customtkinter as ctk

COLORS = {
    "background": "#0B1020",
    "surface": "#111A2E",
    "card": "#151F35",
    "card_hover": "#1B2943",
    "border": "#25324D",
    "accent": "#8B5CF6",
    "accent_hover": "#7544DF",
    "accent_soft": "#282044",
    "text": "#F1F4FC",
    "muted": "#929DB5",
    "success": "#42D6A4",
    "blue": "#60A5FA",
    "orange": "#F5AB62",
    "error": "#FCA5A5",
    "button": "#8B5CF6",
    "button_hover": "#7544DF",
    "selection": "#282044",
    "danger": "#7F1D35",
    "danger_hover": "#9F2444",
}


def apply_theme() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")