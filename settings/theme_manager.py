from __future__ import annotations

import logging
import tkinter as tk
from typing import Any

import customtkinter as ctk

from settings.settings_manager import DEFAULT_SETTINGS
from ui.theme import COLORS

_DARK = {
    "background": "#0B1020", "surface": "#111A2E", "card": "#151F35",
    "card_hover": "#1B2943", "border": "#25324D", "accent": "#8B5CF6",
    "accent_hover": "#7544DF", "accent_soft": "#282044", "text": "#F1F4FC",
    "muted": "#929DB5", "success": "#42D6A4", "blue": "#60A5FA",
    "orange": "#F5AB62", "error": "#FCA5A5", "button": "#8B5CF6",
    "button_hover": "#7544DF", "selection": "#282044",
    "danger": "#7F1D35", "danger_hover": "#9F2444",
}
_LIGHT = {
    "background": "#F4F6FC", "surface": "#E9EDF7", "card": "#FFFFFF",
    "card_hover": "#E5E9F3", "border": "#CDD4E2", "accent": "#6941C6",
    "accent_hover": "#5933B0", "accent_soft": "#E9E1FA", "text": "#182033",
    "muted": "#596579", "success": "#087A55", "blue": "#245EAA",
    "orange": "#9B4C0B", "error": "#B42318", "button": "#6941C6",
    "button_hover": "#5933B0", "selection": "#E9E1FA",
    "danger": "#B42318", "danger_hover": "#912018",
}


def build_palette(settings: dict[str, Any]) -> dict[str, Any]:
    mode = settings.get("theme", "Ciemny")
    if mode == "Jasny":
        palette = dict(_LIGHT)
    elif mode == "Systemowy":
        palette = {key: (_LIGHT[key], _DARK[key]) for key in _DARK}
    elif mode == "Niestandardowy":
        custom = settings.get("custom_colors", DEFAULT_SETTINGS["custom_colors"])
        palette = dict(_DARK)
        palette.update({
            "accent": custom["main"], "accent_hover": _shade(custom["main"], -18),
            "blue": custom["secondary"], "background": custom["background"],
            "surface": _shade(custom["background"], 8), "card": custom["card"],
            "card_hover": _shade(custom["card"], 10), "border": _shade(custom["card"], 20),
            "text": custom["text"], "muted": _blend(custom["text"], custom["card"], 0.58),
            "button": custom["button"], "button_hover": _shade(custom["button"], -18),
            "selection": custom["selection"], "accent_soft": custom["selection"],
            "danger": "#7F1D35", "danger_hover": "#9F2444",
        })
    else:
        palette = dict(_DARK)
    if settings.get("high_contrast"):
        palette["text"] = ("#000000", "#FFFFFF") if mode == "Systemowy" else (
            "#000000" if _is_light(palette["background"]) else "#FFFFFF"
        )
        palette["muted"] = palette["text"]
        palette["border"] = palette["text"]
    return palette


class ThemeManager:
    def __init__(self, root: ctk.CTk, colors: dict[str, Any] = COLORS) -> None:
        self.root = root
        self.colors = colors
        self.settings = dict(DEFAULT_SETTINGS)
        self.logger = logging.getLogger(__name__)
        self._base_fonts: dict[int, tuple[int, str, str]] = {}
        self._base_padding: dict[int, tuple[str, Any, Any]] = {}

    def apply(self, settings: dict[str, Any]) -> None:
        old_palette = dict(self.colors)
        new_palette = build_palette(settings)
        self.colors.clear()
        self.colors.update(new_palette)
        self.settings = dict(settings)
        mode = settings.get("theme", "Ciemny")
        ctk.set_appearance_mode("system" if mode == "Systemowy" else ("light" if mode == "Jasny" else "dark"))
        self.root.configure(fg_color=new_palette["background"])
        self._refresh_tree(self.root, old_palette, new_palette, settings)

    def _refresh_tree(self, parent: tk.Misc, old: dict[str, Any],
                      new: dict[str, Any], settings: dict[str, Any]) -> None:
        for widget in parent.winfo_children():
            self._refresh_widget(widget, old, new, settings)
            self._refresh_tree(widget, old, new, settings)

    def _refresh_widget(self, widget: tk.Misc, old: dict[str, Any],
                        new: dict[str, Any], settings: dict[str, Any]) -> None:
        try:
            keys = widget.configure()
        except tk.TclError:
            return
        if not keys:
            return
        options: dict[str, Any] = {}
        for option in ("fg_color", "hover_color", "button_color", "button_hover_color",
                       "progress_color", "border_color", "text_color",
                       "scrollbar_button_color", "scrollbar_button_hover_color"):
            if option not in keys:
                continue
            try:
                current = widget.cget(option)
            except (tk.TclError, AttributeError):
                continue
            if current == "transparent":
                continue
            mapped = _replace_color(current, option, old, new)
            if mapped is not None:
                options[option] = mapped
        if isinstance(widget, ctk.CTkButton):
            try:
                if widget.cget("fg_color") != "transparent":
                    options["text_color"] = _contrast(new["button"])
            except (tk.TclError, AttributeError):
                pass
        if "font" in keys:
            try:
                font = widget.cget("font")
                if isinstance(font, ctk.CTkFont):
                    base = self._base_fonts.setdefault(
                        id(widget),
                        (int(font.cget("size")), str(font.cget("weight")), str(font.cget("family"))),
                    )
                    options["font"] = ctk.CTkFont(
                        family=settings["font_family"],
                        size=round(base[0] * _font_scale(settings["font_size"])),
                        weight="bold" if settings["bold_text"] else base[1],
                    )
            except (tk.TclError, AttributeError, TypeError, ValueError):
                self.logger.debug("Could not update a widget font", exc_info=True)
        if options:
            try:
                widget.configure(**options)
            except (tk.TclError, ValueError, TypeError):
                self.logger.debug("Could not refresh a widget theme", exc_info=True)
        self._apply_spacing(widget, settings.get("spacing", "Normalne"))

    def _apply_spacing(self, widget: tk.Misc, spacing: str) -> None:
        manager = widget.winfo_manager()
        if manager not in {"grid", "pack"}:
            return
        try:
            info = widget.grid_info() if manager == "grid" else widget.pack_info()
            original = self._base_padding.setdefault(
                id(widget), (manager, info.get("padx", 0), info.get("pady", 0))
            )
            factor = {"Zwarte": 0.75, "Normalne": 1.0, "Przestronne": 1.3}.get(spacing, 1.0)
            geometry = widget.grid_configure if manager == "grid" else widget.pack_configure
            geometry(
                padx=_scale_padding(original[1], factor),
                pady=_scale_padding(original[2], factor),
            )
        except (tk.TclError, TypeError, ValueError):
            self.logger.debug("Could not update widget spacing", exc_info=True)


def _replace_color(value: Any, option: str, old: dict[str, Any],
                   new: dict[str, Any]) -> Any:
    roles = {
        "fg_color": {"background": "background", "surface": "surface", "card": "card",
                     "card_hover": "card_hover", "border": "border", "accent": "button",
                     "accent_hover": "button_hover", "accent_soft": "selection", "blue": "blue",
                     "orange": "orange", "success": "success"},
        "hover_color": {"card_hover": "card_hover", "accent_hover": "button_hover",
                        "accent": "button", "surface": "surface"},
        "button_color": {"accent": "button", "accent_hover": "button_hover"},
        "button_hover_color": {"accent_hover": "button_hover", "accent": "button"},
        "progress_color": {"accent": "accent", "success": "success"},
        "border_color": {"border": "border", "card": "card"},
        "text_color": {"text": "text", "muted": "muted", "accent": "accent",
                       "success": "success", "blue": "blue", "orange": "orange"},
        "scrollbar_button_color": {"border": "border", "surface": "surface"},
        "scrollbar_button_hover_color": {"accent": "accent", "card_hover": "card_hover"},
    }.get(option, {})
    for source, target in roles.items():
        old_value, new_value = old.get(source), new.get(target)
        if old_value is None or new_value is None:
            continue
        if value == old_value:
            return new_value
        if isinstance(value, (tuple, list)) and len(value) == 2:
            if value == old_value or all(part == old_value for part in value):
                return new_value
    legacy = {
        "#FCA5A5": "error",
        "#C4B5FD": "accent",
        "#B9A2FF": "accent",
        "#7F1D35": "danger",
        "#9F2444": "danger_hover",
    }
    for source, target in legacy.items():
        if value == source:
            return new.get(target)
    return None


def _font_scale(size: str) -> float:
    return {"Mały": 0.88, "Normalny": 1.0, "Duży": 1.15, "Bardzo duży": 1.3}.get(size, 1.0)


def _shade(color: str, amount: int) -> str:
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{max(0, min(255, part + amount)):02X}" for part in rgb)


def _blend(first: str, second: str, ratio: float) -> str:
    a = [int(first[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(second[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * ratio + y * (1-ratio)):02X}" for x, y in zip(a, b))


def _is_light(color: str) -> bool:
    if isinstance(color, tuple):
        return _is_light(color[0])
    return sum(int(color[i:i + 2], 16) for i in (1, 3, 5)) > 382


def _contrast(color: str | tuple[str, str]) -> str | tuple[str, str]:
    if isinstance(color, tuple):
        return tuple(_contrast(part) for part in color)
    return "#182033" if _is_light(color) else "#FFFFFF"


def _scale_padding(value: Any, factor: float) -> Any:
    if isinstance(value, (tuple, list)):
        return tuple(round(float(part) * factor) for part in value)
    return round(float(value) * factor)
