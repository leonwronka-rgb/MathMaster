from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox
from uuid import uuid4

import customtkinter as ctk

from flashcards.service import (
    Flashcard,
    FlashcardDeck,
    FlashcardError,
    FlashcardService,
    FlashcardStorageError,
)
from mathematics.topic_library import LIBRARY_TOPICS
from ui.theme import COLORS

_DECK_ALL = "Wszystkie zestawy"
_SORT_LABELS = {
    "Pytanie A–Z": "front",
    "Ostatnio zmienione": "recent",
    "Najbliższa powtórka": "due",
    "Najtrudniejsze": "mastery",
    "Ulubione na górze": "favorite",
}
_RATINGS = (
    ("Nie znam", "again"),
    ("Trudne", "hard"),
    ("Umiem", "know"),
    ("Łatwe", "easy"),
)


class FlashcardScreen(ctk.CTkFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        user_id: int,
        service: FlashcardService,
        on_gamification_update: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self.user_id = user_id
        self.service = service
        self.on_gamification_update = on_gamification_update
        self.cards: tuple[Flashcard, ...] = ()
        self.decks: tuple[FlashcardDeck, ...] = ()
        self.current_queue: tuple[Flashcard, ...] = ()
        self.current_index = 0
        self.current_card: Flashcard | None = None
        self.revealed = False
        self.mode = "Nauka"
        self.test_session_id = ""
        self.test_correct: bool | None = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(2, 10))
        ctk.CTkLabel(
            header,
            text="Fiszki matematyczne",
            anchor="w",
            font=ctk.CTkFont(size=27, weight="bold"),
            text_color=COLORS["text"],
        ).pack(side="left")
        self.mode_menu = ctk.CTkOptionMenu(
            header,
            values=["Nauka", "Test"],
            command=self._mode_changed,
            fg_color=COLORS["surface"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
        )
        self.mode_menu.set("Nauka")
        self.mode_menu.pack(side="right")

        self.stats_label = ctk.CTkLabel(
            self, text="", anchor="w", text_color=COLORS["muted"]
        )
        self.stats_label.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=2, uniform="cards")
        body.grid_columnconfigure(1, weight=3, uniform="cards")
        body.grid_rowconfigure(0, weight=1)
        self.collection = ctk.CTkFrame(
            body, fg_color=COLORS["card"], corner_radius=16,
            border_color=COLORS["border"], border_width=1,
        )
        self.collection.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.collection.grid_columnconfigure(0, weight=1)
        self.study = ctk.CTkScrollableFrame(
            body, fg_color=COLORS["card"], corner_radius=16,
            border_color=COLORS["border"], border_width=1,
        )
        self.study.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.study.grid_columnconfigure(0, weight=1)
        self._build_collection_controls()
        self._build_study_controls()
        self.refresh()

    def _build_collection_controls(self) -> None:
        ctk.CTkLabel(
            self.collection,
            text="Twoje zestawy i fiszki",
            anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        self.deck_menu = ctk.CTkOptionMenu(
            self.collection,
            values=[_DECK_ALL],
            command=lambda _: self.refresh_cards(),
        )
        self.deck_menu.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        self.search_entry = ctk.CTkEntry(
            self.collection, placeholder_text="Szukaj fiszek…"
        )
        self.search_entry.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
        self.search_entry.bind("<KeyRelease>", lambda _: self.refresh_cards())
        filters = ctk.CTkFrame(self.collection, fg_color="transparent")
        filters.grid(row=3, column=0, sticky="ew", padx=12, pady=3)
        filters.grid_columnconfigure((0, 1), weight=1)
        self.sort_menu = ctk.CTkOptionMenu(
            filters,
            values=list(_SORT_LABELS),
            command=lambda _: self.refresh_cards(),
        )
        self.sort_menu.set("Pytanie A–Z")
        self.sort_menu.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.favorite_filter = ctk.CTkOptionMenu(
            filters,
            values=["Wszystkie", "Ulubione"],
            command=lambda _: self.refresh_cards(),
        )
        self.favorite_filter.set("Wszystkie")
        self.favorite_filter.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.card_list = ctk.CTkScrollableFrame(
            self.collection, fg_color="transparent", height=300
        )
        self.card_list.grid(row=4, column=0, sticky="nsew", padx=6, pady=4)
        self.collection.grid_rowconfigure(4, weight=1)
        actions = ctk.CTkFrame(self.collection, fg_color="transparent")
        actions.grid(row=5, column=0, sticky="ew", padx=10, pady=(2, 5))
        actions.grid_columnconfigure((0, 1), weight=1)
        for index, (label, command) in enumerate((
            ("＋ Fiszka", self._open_create_card),
            ("Z tematu", self._create_from_topic),
            ("＋ Zestaw", self._create_deck),
            ("Edytuj", self._edit_selected),
            ("Usuń", self._delete_selected),
            ("☆ Ulubione", self._toggle_selected_favorite),
        )):
            ctk.CTkButton(
                actions,
                text=label,
                command=command,
                fg_color=COLORS["surface"],
                hover_color=COLORS["card_hover"],
            ).grid(
                row=index // 2, column=index % 2, padx=2, pady=2,
                sticky="ew",
            )
        deck_actions = ctk.CTkFrame(self.collection, fg_color="transparent")
        deck_actions.grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 3))
        ctk.CTkButton(
            deck_actions, text="Zmień nazwę zestawu", command=self._rename_deck,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
        ).pack(side="left", padx=2, expand=True, fill="x")
        ctk.CTkButton(
            deck_actions, text="Usuń zestaw", command=self._delete_deck,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
        ).pack(side="left", padx=2, expand=True, fill="x")
        file_actions = ctk.CTkFrame(self.collection, fg_color="transparent")
        file_actions.grid(row=7, column=0, sticky="ew", padx=10, pady=(0, 10))
        ctk.CTkButton(
            file_actions, text="Import JSON", command=self._import_json,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
        ).pack(side="left", padx=2, expand=True, fill="x")
        ctk.CTkButton(
            file_actions, text="Eksport JSON", command=self._export_json,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
        ).pack(side="left", padx=2, expand=True, fill="x")
        self.collection_status = ctk.CTkLabel(
            self.collection, text="", anchor="w", wraplength=380,
            text_color=COLORS["muted"],
        )
        self.collection_status.grid(row=8, column=0, sticky="ew", padx=12, pady=(0, 8))

    def _build_study_controls(self) -> None:
        ctk.CTkLabel(
            self.study,
            text="Powtórka",
            anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 4))
        options = ctk.CTkFrame(self.study, fg_color="transparent")
        options.grid(row=1, column=0, sticky="ew", padx=12)
        self.random_toggle = ctk.CTkCheckBox(options, text="Losowo")
        self.random_toggle.pack(side="left", padx=4)
        self.difficult_toggle = ctk.CTkCheckBox(options, text="Tylko trudne")
        self.difficult_toggle.pack(side="left", padx=4)
        self.start_button = ctk.CTkButton(
            options,
            text="Rozpocznij powtórkę",
            command=self.start_study,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        )
        self.start_button.pack(side="right", padx=4)
        self.card_counter = ctk.CTkLabel(
            self.study, text="Wybierz fiszkę lub rozpocznij powtórkę.",
            anchor="center", text_color=COLORS["muted"],
        )
        self.card_counter.grid(row=2, column=0, sticky="ew", padx=14, pady=(14, 4))
        self.card_surface = ctk.CTkFrame(
            self.study, fg_color=COLORS["surface"], corner_radius=18,
            border_color=COLORS["border"], border_width=1, height=230,
        )
        self.card_surface.grid(row=3, column=0, sticky="ew", padx=14, pady=8)
        self.card_surface.grid_columnconfigure(0, weight=1)
        self.card_surface.grid_rowconfigure(0, weight=1)
        self.card_surface.grid_propagate(False)
        self.card_text = ctk.CTkLabel(
            self.card_surface,
            text="Wybierz fiszkę z listy albo rozpocznij powtórkę.",
            justify="center",
            wraplength=650,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLORS["text"],
        )
        self.card_text.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.test_entry = ctk.CTkEntry(
            self.study, placeholder_text="Wpisz odpowiedź w trybie testowym…"
        )
        self.test_entry.grid(row=4, column=0, sticky="ew", padx=14, pady=(2, 5))
        self.flip_button = ctk.CTkButton(
            self.study, text="Odwróć kartę", command=self._flip_card
        )
        self.flip_button.grid(row=5, column=0, sticky="ew", padx=14, pady=5)
        self.rating_frame = ctk.CTkFrame(self.study, fg_color="transparent")
        self.rating_frame.grid(row=6, column=0, sticky="ew", padx=10, pady=(5, 14))
        for label, rating in _RATINGS:
            ctk.CTkButton(
                self.rating_frame,
                text=label,
                command=lambda selected=rating: self._rate(selected),
                fg_color=COLORS["accent"] if rating in {"know", "easy"} else COLORS["surface"],
                hover_color=COLORS["accent_hover"] if rating in {"know", "easy"} else COLORS["card_hover"],
                width=100,
            ).pack(side="left", padx=3, expand=True, fill="x")
        self.feedback = ctk.CTkLabel(
            self.study, text="", anchor="w", wraplength=650,
            text_color=COLORS["muted"],
        )
        self.feedback.grid(row=7, column=0, sticky="ew", padx=14, pady=(0, 14))
        goal = ctk.CTkFrame(
            self.study, fg_color=COLORS["surface"], corner_radius=12
        )
        goal.grid(row=8, column=0, sticky="ew", padx=14, pady=(0, 14))
        ctk.CTkLabel(goal, text="Dzienny cel:", anchor="w").pack(
            side="left", padx=(10, 4), pady=8
        )
        self.goal_entry = ctk.CTkEntry(goal, width=70, justify="center")
        self.goal_entry.pack(side="left", padx=4, pady=8)
        self.goal_button = ctk.CTkButton(
            goal, text="Zapisz", width=70, command=self._save_goal
        )
        self.goal_button.pack(side="left", padx=4, pady=8)
        self.goal_progress = ctk.CTkProgressBar(
            goal, progress_color=COLORS["accent"], fg_color=COLORS["border"]
        )
        self.goal_progress.pack(side="left", padx=10, pady=8, expand=True, fill="x")

    def refresh(self) -> None:
        try:
            self.decks = self.service.get_decks(self.user_id)
            stats = self.service.get_stats(self.user_id)
            self.stats_label.configure(text=self._stats_text())
            self.goal_progress.set(stats.goal_progress)
            self.goal_entry.delete(0, "end")
            self.goal_entry.insert(0, str(self.service.get_stats(self.user_id).daily_goal))
            self.refresh_cards()
        except (FlashcardStorageError, FlashcardError) as error:
            self._message(str(error), error=True)

    def _stats_text(self) -> str:
        stats = self.service.get_stats(self.user_id)
        return (
            f"Fiszki: {stats.total_cards}   ·   Opanowane: {stats.mastered_cards}"
            f"   ·   Do powtórki: {stats.due_cards}   ·   Dziś: "
            f"{stats.studied_today}/{stats.daily_goal}   ·   Skuteczność dziś: "
            f"{stats.accuracy_percent:.1f}%   ·   Seria: {stats.streak_days} dni"
        )

    def refresh_cards(self) -> None:
        if not hasattr(self, "card_list"):
            return
        for child in self.card_list.winfo_children():
            child.destroy()
        try:
            selected_deck = self.deck_menu.get()
            deck_id = next(
                (deck.id for deck in self.decks if deck.name == selected_deck), None
            )
            if selected_deck == _DECK_ALL:
                deck_id = None
            self.cards = self.service.list_cards(
                self.user_id,
                search=self.search_entry.get(),
                deck_id=deck_id,
                favorites_only=self.favorite_filter.get() == "Ulubione",
                sort_by=_SORT_LABELS[self.sort_menu.get()],
            )
        except (FlashcardError, FlashcardStorageError, KeyError) as error:
            self._message(str(error), error=True)
            return
        for card in self.cards:
            ctk.CTkButton(
                self.card_list,
                text=f"{'★ ' if card.favorite else ''}{card.front}",
                anchor="w",
                height=44,
                fg_color=COLORS["surface"],
                hover_color=COLORS["card_hover"],
                command=lambda selected=card: self._select_card(selected),
            ).pack(fill="x", padx=4, pady=3)
        if not self.cards:
            ctk.CTkLabel(
                self.card_list,
                text="Brak fiszek. Dodaj własną lub utwórz je z tematu.",
                wraplength=330,
                text_color=COLORS["muted"],
            ).pack(fill="x", padx=8, pady=15)
        self.deck_menu.configure(
            values=[_DECK_ALL, *(deck.name for deck in self.decks)]
        )
        if self.deck_menu.get() not in {_DECK_ALL, *(deck.name for deck in self.decks)}:
            self.deck_menu.set(_DECK_ALL)

    def _select_card(self, card: Flashcard) -> None:
        self.current_card = card
        self.current_queue = (card,)
        self.current_index = 0
        self._show_front()

    def start_study(self) -> None:
        try:
            selected_deck = self.deck_menu.get()
            deck_id = next(
                (deck.id for deck in self.decks if deck.name == selected_deck), None
            )
            all_cards = self.service.get_all_cards_for_study(
                self.user_id,
                deck_id=deck_id,
                difficult_only=bool(self.difficult_toggle.get()),
                random_order=bool(self.random_toggle.get()),
            )
            due_cards = self.service.get_due_cards(
                self.user_id,
                deck_id=deck_id,
                difficult_only=bool(self.difficult_toggle.get()),
                random_order=bool(self.random_toggle.get()),
            )
            self.current_queue = (
                all_cards if self.mode == "Test" else due_cards or all_cards
            )
        except (FlashcardError, FlashcardStorageError) as error:
            self._message(str(error), error=True)
            return
        if not self.current_queue:
            self.current_card = None
            self.card_text.configure(text="Brak fiszek w tym zestawie.")
            self.card_counter.configure(text="Utwórz fiszki lub zmień filtry.")
            return
        self.test_session_id = str(uuid4()) if self.mode == "Test" else ""
        if not due_cards:
            self.feedback.configure(
                text="Nie ma zaległych powtórek — pokazuję fiszki z zestawu do swobodnej nauki."
            )
        else:
            self.feedback.configure(text="")
        self.current_index = 0
        self.current_card = self.current_queue[0]
        self._show_front()

    def _show_front(self) -> None:
        self.revealed = False
        self.test_correct = None
        if self.current_card is None:
            return
        self.card_text.configure(text=self.current_card.front)
        self.card_counter.configure(
            text=f"{self.current_index + 1} / {len(self.current_queue)}"
            if len(self.current_queue) > 1
            else f"{self.current_card.deck_name} · poziom opanowania {self.current_card.mastery}/5"
        )
        self.flip_button.configure(text="Sprawdź i odwróć" if self.mode == "Test" else "Odwróć kartę")
        self.test_entry.grid() if self.mode == "Test" else self.test_entry.grid_remove()
        self.rating_frame.grid_remove()
        self.test_entry.delete(0, "end")

    def _flip_card(self) -> None:
        if self.current_card is None:
            return
        if self.mode == "Test":
            submitted = self.test_entry.get().strip().casefold()
            expected = self.current_card.back.splitlines()[0].strip().casefold()
            self.test_correct = bool(submitted and submitted == expected)
            self.feedback.configure(
                text=(
                    "Odpowiedź poprawna."
                    if submitted and submitted == expected
                    else f"Sprawdź odpowiedź. Poprawna: {self.current_card.back}"
                )
            )
        self.revealed = True
        self.card_text.configure(text=self.current_card.back)
        self.flip_button.configure(text="Odpowiedź")
        self.rating_frame.grid()

    def _rate(self, rating: str) -> None:
        if self.current_card is None or not self.revealed:
            self.feedback.configure(text="Najpierw odwróć kartę, aby sprawdzić odpowiedź.")
            return
        try:
            result = self.service.review(
                self.user_id,
                self.current_card.id,
                rating,
                test_correct=self.test_correct if self.mode == "Test" else None,
                test_session_id=self.test_session_id if self.mode == "Test" else "",
            )
            self.feedback.configure(
                text=f"Zapisano powtórkę. Następna: {result.next_review_at} · "
                f"opanowanie {result.mastery}/5."
            )
            self.stats_label.configure(text=self._stats_text())
            self.goal_progress.set(self.service.get_stats(self.user_id).goal_progress)
            self.refresh_cards()
            self.current_index += 1
            if self.current_index < len(self.current_queue):
                self.current_card = self.current_queue[self.current_index]
                self._show_front()
            else:
                self.current_card = None
                self.card_text.configure(text="Sesja zakończona. Dobra praca!")
                self.card_counter.configure(
                    text=f"Przejrzano {len(self.current_queue)} fiszek."
                )
                self.rating_frame.grid_remove()
            if self.on_gamification_update is not None:
                self.on_gamification_update()
        except (FlashcardError, FlashcardStorageError) as error:
            self._message(str(error), error=True)

    def _mode_changed(self, mode: str) -> None:
        self.mode = mode
        self.test_session_id = str(uuid4()) if mode == "Test" else ""
        if self.current_card is not None:
            self._show_front()

    def _create_deck(self) -> None:
        dialog = ctk.CTkInputDialog(text="Nazwa nowego zestawu:", title="Nowy zestaw")
        name = dialog.get_input()
        if not name:
            return
        try:
            self.service.create_deck(self.user_id, name)
            self.decks = self.service.get_decks(self.user_id)
            self.deck_menu.configure(values=[_DECK_ALL, *(deck.name for deck in self.decks)])
            self.deck_menu.set(name.strip())
            self.refresh_cards()
            self._message("Utworzono zestaw.")
        except (FlashcardError, FlashcardStorageError) as error:
            self._message(str(error), error=True)

    def _selected_deck(self) -> FlashcardDeck | None:
        selected = self.deck_menu.get()
        return next((deck for deck in self.decks if deck.name == selected), None)

    def _rename_deck(self) -> None:
        deck = self._selected_deck()
        if deck is None:
            self._message("Wybierz zestaw z listy.", error=True)
            return
        dialog = ctk.CTkInputDialog(text="Nowa nazwa zestawu:", title="Zmień nazwę")
        name = dialog.get_input()
        if not name:
            return
        try:
            self.service.rename_deck(self.user_id, deck.id, name)
            self.refresh()
            self.deck_menu.set(name.strip())
        except (FlashcardError, FlashcardStorageError) as error:
            self._message(str(error), error=True)

    def _delete_deck(self) -> None:
        deck = self._selected_deck()
        if deck is None:
            self._message("Wybierz zestaw z listy.", error=True)
            return
        if not messagebox.askyesno(
            "Usuń zestaw?",
            f"Usunięty zostanie zestaw „{deck.name}”. Fiszki pozostaną na koncie.",
            parent=self,
        ):
            return
        try:
            self.service.delete_deck(self.user_id, deck.id)
            self.deck_menu.set(_DECK_ALL)
            self.refresh()
        except (FlashcardError, FlashcardStorageError) as error:
            self._message(str(error), error=True)

    def _toggle_selected_favorite(self) -> None:
        if self.current_card is None:
            self._message("Wybierz fiszkę z listy.", error=True)
            return
        try:
            favorite = self.service.toggle_favorite(
                self.user_id, self.current_card.id
            )
            self.current_card = self.service.get_card(
                self.user_id, self.current_card.id
            )
            self._message(
                "Dodano do ulubionych." if favorite else "Usunięto z ulubionych."
            )
            self.refresh_cards()
        except (FlashcardError, FlashcardStorageError) as error:
            self._message(str(error), error=True)

    def _create_from_topic(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Utwórz fiszki z tematu")
        dialog.geometry("520x235")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)
        topics = {
            f"{topic.division} › {topic.subdivision} › {topic.title}": topic
            for topic in LIBRARY_TOPICS
        }
        selector = ctk.CTkOptionMenu(dialog, values=list(topics))
        selector.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        amount = ctk.CTkEntry(dialog, placeholder_text="Liczba fiszek (1–50)")
        amount.insert(0, "5")
        amount.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        feedback = ctk.CTkLabel(dialog, text="", text_color="#FCA5A5")
        feedback.grid(row=2, column=0, sticky="ew", padx=16, pady=4)

        def generate() -> None:
            deck = self._selected_deck()
            try:
                created = self.service.create_from_topic(
                    self.user_id,
                    topics[selector.get()],
                    count=int(amount.get()),
                    deck_id=deck.id if deck else None,
                )
                dialog.destroy()
                self.refresh()
                self._message(f"Utworzono fiszek: {len(created)}.")
                if self.on_gamification_update is not None:
                    self.on_gamification_update()
            except (ValueError, FlashcardError, FlashcardStorageError) as error:
                feedback.configure(text=str(error))

        ctk.CTkButton(
            dialog,
            text="Utwórz fiszki",
            command=generate,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
        ).grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 16))

    def _open_create_card(self) -> None:
        self._open_card_dialog()

    def _edit_selected(self) -> None:
        if self.current_card is None:
            self._message("Wybierz fiszkę z listy.", error=True)
            return
        self._open_card_dialog(self.current_card)

    def _open_card_dialog(self, card: Flashcard | None = None) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Edytuj fiszkę" if card else "Nowa fiszka")
        dialog.geometry("540x560")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            dialog, text="Pytanie", anchor="w"
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 3))
        front = ctk.CTkTextbox(dialog, height=85)
        front.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))
        ctk.CTkLabel(dialog, text="Odpowiedź", anchor="w").grid(
            row=2, column=0, sticky="ew", padx=18, pady=3
        )
        back = ctk.CTkTextbox(dialog, height=110)
        back.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 8))
        deck_menu = ctk.CTkOptionMenu(
            dialog, values=[deck.name for deck in self.decks] or ["Moje fiszki"]
        )
        deck_menu.grid(row=4, column=0, sticky="ew", padx=18, pady=5)
        if card:
            deck_menu.set(card.deck_name)
        division_menu = ctk.CTkOptionMenu(
            dialog,
            values=["Bez działu", *(division.title for division in LIBRARY_DIVISIONS)],
        )
        division_menu.grid(row=5, column=0, sticky="ew", padx=18, pady=5)
        topic_names = {topic.id: topic.title for topic in LIBRARY_TOPICS}
        topic_values = ["Bez tematu", *topic_names.values()]
        topic_menu = ctk.CTkOptionMenu(dialog, values=topic_values)
        topic_menu.grid(row=6, column=0, sticky="ew", padx=18, pady=5)
        if card:
            front.insert("1.0", card.front)
            back.insert("1.0", card.back)
            division_menu.set(card.division or "Bez działu")
            topic_menu.set(topic_names.get(card.topic_id, "Bez tematu"))
        favorite = ctk.CTkCheckBox(dialog, text="Ulubiona")
        favorite.grid(row=7, column=0, sticky="w", padx=18, pady=8)
        if card and card.favorite:
            favorite.select()
        feedback = ctk.CTkLabel(dialog, text="", text_color="#FCA5A5")
        feedback.grid(row=8, column=0, sticky="ew", padx=18, pady=3)

        def save() -> None:
            selected_deck_name = deck_menu.get()
            selected_deck = next(
                (deck for deck in self.decks if deck.name == selected_deck_name), None
            )
            try:
                if card:
                    saved = self.service.update_card(
                        self.user_id,
                        card.id,
                        front.get("1.0", "end"),
                        back.get("1.0", "end"),
                        deck_id=selected_deck.id if selected_deck else None,
                        division="" if division_menu.get() == "Bez działu" else division_menu.get(),
                        topic_id=next(
                            (key for key, value in topic_names.items() if value == topic_menu.get()),
                            "",
                        ),
                    )
                    if bool(favorite.get()) != saved.favorite:
                        self.service.toggle_favorite(self.user_id, saved.id)
                else:
                    created = self.service.create_card(
                        self.user_id,
                        front.get("1.0", "end"),
                        back.get("1.0", "end"),
                        deck_id=selected_deck.id if selected_deck else None,
                        division="" if division_menu.get() == "Bez działu" else division_menu.get(),
                        topic_id=next(
                            (key for key, value in topic_names.items() if value == topic_menu.get()),
                            "",
                        ),
                    )
                    if favorite.get():
                        self.service.toggle_favorite(self.user_id, created.id)
                dialog.destroy()
                self.refresh()
                if card is None and self.on_gamification_update is not None:
                    self.on_gamification_update()
            except (FlashcardError, FlashcardStorageError) as error:
                feedback.configure(text=str(error))

        ctk.CTkButton(
            dialog, text="Zapisz fiszkę", command=save,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        ).grid(row=9, column=0, sticky="ew", padx=18, pady=(8, 18))

    def _delete_selected(self) -> None:
        if self.current_card is None:
            self._message("Wybierz fiszkę z listy.", error=True)
            return
        if not messagebox.askyesno(
            "Usuń fiszkę?",
            "Fiszka i jej historia powtórek zostaną usunięte.",
            parent=self,
        ):
            return
        try:
            self.service.delete_card(self.user_id, self.current_card.id)
            self.current_card = None
            self.card_text.configure(text="Wybierz fiszkę z listy.")
            self.refresh()
        except (FlashcardError, FlashcardStorageError) as error:
            self._message(str(error), error=True)

    def _import_json(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Importuj fiszki JSON",
            filetypes=(("Pliki JSON", "*.json"), ("Wszystkie pliki", "*.*")),
        )
        if not path:
            return
        try:
            if Path(path).stat().st_size > 5_000_000:
                raise FlashcardError("Plik JSON przekracza limit 5 MB.")
            content = Path(path).read_text(encoding="utf-8")
            imported = self.service.import_json(self.user_id, content)
            self.refresh()
            self._message(f"Zaimportowano fiszek: {imported}.")
            if imported and self.on_gamification_update is not None:
                self.on_gamification_update()
        except (OSError, FlashcardError, FlashcardStorageError) as error:
            self._message(str(error), error=True)

    def _export_json(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Eksportuj fiszki JSON",
            defaultextension=".json",
            filetypes=(("Pliki JSON", "*.json"),),
        )
        if not path:
            return
        selected_deck_name = self.deck_menu.get()
        deck_id = next(
            (deck.id for deck in self.decks if deck.name == selected_deck_name), None
        )
        try:
            content = self.service.export_json(
                self.user_id, deck_id=None if selected_deck_name == _DECK_ALL else deck_id
            )
            Path(path).write_text(content, encoding="utf-8")
            self._message("Eksport fiszek został zapisany.")
        except (OSError, FlashcardStorageError) as error:
            self._message(str(error), error=True)

    def _save_goal(self) -> None:
        try:
            self.service.set_daily_goal(self.user_id, int(self.goal_entry.get()))
            self.stats_label.configure(text=self._stats_text())
            self._message("Zapisano dzienny cel.")
        except (ValueError, FlashcardError, FlashcardStorageError) as error:
            self._message(str(error), error=True)

    def _message(self, text: str, *, error: bool = False) -> None:
        self.collection_status.configure(
            text=text,
            text_color="#FCA5A5" if error else COLORS["success"],
        )

