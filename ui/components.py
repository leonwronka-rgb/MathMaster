from __future__ import annotations

import customtkinter as ctk


def create_page_title(parent: ctk.CTkBaseClass, title: str) -> ctk.CTkLabel:
    label = ctk.CTkLabel(
        parent,
        text=title,
        anchor="w",
        font=ctk.CTkFont(size=28, weight="bold"),
    )
    label.pack(fill="x", pady=(8, 16))
    return label