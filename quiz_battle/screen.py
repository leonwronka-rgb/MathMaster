from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from mathematics.topics import DIFFICULTY_NAMES, TOPIC_CATEGORIES
from quiz_battle.client import QuizBattleConnectionError
from quiz_battle.service import BattleHistoryItem, QuizBattleService
from ui.theme import COLORS

_MODE_LABELS = {
    "Wyścig na czas": "race",
    "Do trzech pomyłek": "survival",
}
_MODE_TITLES = {value: key for key, value in _MODE_LABELS.items()}
_DIFFICULTIES = tuple(DIFFICULTY_NAMES)
_CATEGORIES = tuple(TOPIC_CATEGORIES)
_RANKING_SORTS = {
    "Zwycięstwa": "wins",
    "Punkty": "points",
    "Skuteczność": "win_rate",
}


class QuizBattleScreen(ctk.CTkFrame):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        user_id: int,
        display_name: str,
        service: QuizBattleService,
        *,
        server_url: str = "",
        server_token: str = "",
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self.user_id = user_id
        self.display_name = display_name
        self.service = service
        self._disposed = False
        self._pending_action: Callable[[], None] | None = None
        self._active_match_id = ""
        self._active_room_code = ""
        self._current_question_id = ""
        self._last_battle_id = ""
        self._players: list[dict[str, object]] = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.service.set_listener(self._queue_server_event)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text="Quiz Battle", anchor="w",
            font=ctk.CTkFont(size=27, weight="bold"), text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="w")
        self.connection_status = ctk.CTkLabel(
            header, text="● Rozłączono", text_color=COLORS["muted"],
        )
        self.connection_status.grid(row=0, column=1, sticky="e")
        self.status_label = ctk.CTkLabel(
            self, text="Połącz się z serwerem, aby grać z prawdziwymi użytkownikami.",
            anchor="w", wraplength=900, text_color=COLORS["muted"],
        )
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        self.overview = ctk.CTkScrollableFrame(
            self, fg_color="transparent", scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.overview.grid(row=1, column=0, sticky="nsew")
        self.overview.grid_columnconfigure((0, 1), weight=1, uniform="battle")
        self._build_overview(server_url, server_token)

        self.match_view = ctk.CTkFrame(
            self, fg_color=COLORS["card"], corner_radius=18,
            border_color=COLORS["border"], border_width=1,
        )
        self.match_view.grid(row=1, column=0, sticky="nsew")
        self.match_view.grid_columnconfigure(0, weight=3)
        self.match_view.grid_columnconfigure(1, weight=2)
        self.match_view.grid_rowconfigure(1, weight=1)
        self.match_view.grid_remove()
        self._build_match_view()

        self.result_view = ctk.CTkFrame(
            self, fg_color=COLORS["card"], corner_radius=18,
            border_color=COLORS["border"], border_width=1,
        )
        self.result_view.grid(row=1, column=0, sticky="nsew")
        self.result_view.grid_columnconfigure(0, weight=1)
        self.result_view.grid_rowconfigure(2, weight=1)
        self.result_view.grid_remove()
        self._build_result_view()
        self._refresh_local_data()
        if self.service.authenticated:
            self.connection_status.configure(
                text="● Połączono", text_color=COLORS["success"]
            )
            self.service.resume_active_match()
            self._request_leaderboard()

    def _build_overview(self, server_url: str, server_token: str) -> None:
        connection = self._card(self.overview, row=0, column=0, colspan=2)
        ctk.CTkLabel(
            connection, text="Połączenie z serwerem", anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text"],
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(12, 6))
        connection.grid_columnconfigure(1, weight=1)
        self.url_entry = ctk.CTkEntry(
            connection, placeholder_text="wss://twoj-serwer.example/quiz-battle",
        )
        self.url_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=5)
        if server_url:
            self.url_entry.insert(0, server_url)
        self.token_entry = ctk.CTkEntry(
            connection, placeholder_text="Token gracza z serwera", show="•",
        )
        self.token_entry.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 12))
        if server_token:
            self.token_entry.insert(0, server_token)
        ctk.CTkButton(
            connection, text="Połącz", command=self._connect,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        ).grid(row=1, column=2, rowspan=2, padx=12, pady=6)

        self.stats_card = self._card(self.overview, row=1, column=0)
        ctk.CTkLabel(
            self.stats_card, text="Statystyki gracza", anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=14, pady=(12, 6))
        self.stats_text = ctk.CTkLabel(
            self.stats_card, text="Brak rozegranych pojedynków.",
            anchor="w", justify="left", wraplength=430, text_color=COLORS["muted"],
        )
        self.stats_text.pack(fill="x", padx=14, pady=(0, 14))

        settings = self._card(self.overview, row=1, column=1)
        ctk.CTkLabel(
            settings, text="Ustawienia pojedynku", anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=14, pady=(12, 6))
        self.mode_menu = ctk.CTkOptionMenu(
            settings, values=list(_MODE_LABELS), command=self._mode_changed,
            fg_color=COLORS["surface"],
            button_color=COLORS["accent"],
        )
        self.mode_menu.set("Wyścig na czas")
        self.mode_menu.pack(fill="x", padx=12, pady=4)
        duration_row = ctk.CTkFrame(settings, fg_color="transparent")
        duration_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(duration_row, text="Czas (wyścig):").pack(side="left", padx=(0, 8))
        self.duration_menu = ctk.CTkOptionMenu(
            duration_row, values=["60", "120", "180"], width=92,
            fg_color=COLORS["surface"], button_color=COLORS["accent"],
        )
        self.duration_menu.set("60")
        self.duration_menu.pack(side="right")
        players_row = ctk.CTkFrame(settings, fg_color="transparent")
        players_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(players_row, text="Gracze:").pack(side="left", padx=(0, 8))
        self.players_menu = ctk.CTkOptionMenu(
            players_row, values=[str(count) for count in range(2, 9)], width=92,
            fg_color=COLORS["surface"], button_color=COLORS["accent"],
        )
        self.players_menu.set("2")
        self.players_menu.pack(side="right")
        self.category_menu = ctk.CTkOptionMenu(
            settings, values=list(_CATEGORIES), command=self._category_changed,
            fg_color=COLORS["surface"], button_color=COLORS["accent"],
        )
        self.category_menu.set(_CATEGORIES[0])
        self.category_menu.pack(fill="x", padx=12, pady=4)
        self.difficulty_menu = ctk.CTkOptionMenu(
            settings,
            values=[DIFFICULTY_NAMES[level] for level in _DIFFICULTIES],
            fg_color=COLORS["surface"], button_color=COLORS["accent"],
        )
        self.difficulty_menu.set(DIFFICULTY_NAMES[3])
        self.difficulty_menu.pack(fill="x", padx=12, pady=4)
        self.topic_checks = ctk.CTkScrollableFrame(
            settings, height=96, fg_color=COLORS["surface"], corner_radius=10,
        )
        self.topic_checks.pack(fill="x", padx=12, pady=5)
        self._render_topics(_CATEGORIES[0])
        actions = ctk.CTkFrame(settings, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=(5, 12))
        ctk.CTkButton(
            actions, text="Szybka gra", command=self._quick_game,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        ).pack(fill="x", padx=2, pady=3)
        ctk.CTkButton(
            actions, text="Gra ze znajomym · utwórz pokój",
            command=self._create_room, fg_color=COLORS["surface"],
            hover_color=COLORS["card_hover"],
        ).pack(fill="x", padx=2, pady=3)
        join = ctk.CTkFrame(actions, fg_color="transparent")
        join.pack(fill="x", pady=3)
        self.room_entry = ctk.CTkEntry(join, placeholder_text="Kod pokoju")
        self.room_entry.pack(side="left", expand=True, fill="x", padx=(2, 5))
        ctk.CTkButton(
            join, text="Dołącz", width=85, command=self._join_room,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
        ).pack(side="right", padx=(5, 2))

        self.history_card = self._card(self.overview, row=2, column=0)
        ctk.CTkLabel(
            self.history_card, text="Historia pojedynków", anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=14, pady=(12, 5))
        self.history_text = ctk.CTkLabel(
            self.history_card, text="", anchor="w", justify="left",
            wraplength=430, text_color=COLORS["muted"],
        )
        self.history_text.pack(fill="x", padx=14, pady=(0, 12))

        self.ranking_card = self._card(self.overview, row=2, column=1)
        ranking_header = ctk.CTkFrame(self.ranking_card, fg_color="transparent")
        ranking_header.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(
            ranking_header, text="Ranking Quiz Battle", anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text"],
        ).pack(side="left")
        self.leaderboard_sort = ctk.CTkOptionMenu(
            ranking_header, values=list(_RANKING_SORTS),
            command=lambda _: self._request_leaderboard(),
            width=120, fg_color=COLORS["surface"], button_color=COLORS["accent"],
        )
        self.leaderboard_sort.set("Zwycięstwa")
        self.leaderboard_sort.pack(side="right", padx=(5, 0))
        ctk.CTkButton(
            ranking_header, text="Odśwież", width=76,
            command=self._request_leaderboard,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
        ).pack(side="right")
        self.ranking_text = ctk.CTkLabel(
            self.ranking_card,
            text="Ranking online wczyta się po połączeniu z serwerem.",
            anchor="w", justify="left", wraplength=430, text_color=COLORS["muted"],
        )
        self.ranking_text.pack(fill="x", padx=14, pady=(0, 12))

    def _build_match_view(self) -> None:
        header = ctk.CTkFrame(self.match_view, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=12)
        header.grid_columnconfigure(0, weight=1)
        self.match_title = ctk.CTkLabel(
            header, text="Oczekiwanie na graczy", anchor="w",
            font=ctk.CTkFont(size=20, weight="bold"), text_color=COLORS["text"],
        )
        self.match_title.grid(row=0, column=0, sticky="w")
        self.match_timer = ctk.CTkLabel(
            header, text="—", font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["accent"],
        )
        self.match_timer.grid(row=0, column=1, padx=12)
        ctk.CTkButton(
            header, text="Wyjdź", width=78, command=self._leave_match,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
        ).grid(row=0, column=2)
        self.match_progress = ctk.CTkProgressBar(
            self.match_view, progress_color=COLORS["accent"], fg_color=COLORS["border"],
        )
        self.match_progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
        question_panel = ctk.CTkFrame(
            self.match_view, fg_color=COLORS["surface"], corner_radius=14,
        )
        question_panel.grid(row=2, column=0, sticky="nsew", padx=(16, 8), pady=(0, 16))
        question_panel.grid_columnconfigure(0, weight=1)
        self.question_label = ctk.CTkLabel(
            question_panel, text="Pytanie pojawi się po rozpoczęciu meczu.",
            justify="center", wraplength=650,
            font=ctk.CTkFont(size=23, weight="bold"), text_color=COLORS["text"],
        )
        self.question_label.pack(expand=True, fill="both", padx=24, pady=24)
        answer_row = ctk.CTkFrame(question_panel, fg_color="transparent")
        answer_row.pack(fill="x", padx=16, pady=(0, 16))
        self.answer_entry = ctk.CTkEntry(
            answer_row, placeholder_text="Wpisz odpowiedź",
        )
        self.answer_entry.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.answer_entry.bind("<Return>", lambda _: self._submit_answer())
        self.answer_button = ctk.CTkButton(
            answer_row, text="Odpowiedz", command=self._submit_answer, width=120,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        )
        self.answer_button.pack(side="right", padx=(6, 0))
        self.live_score = ctk.CTkLabel(
            question_panel, text="Punkty: 0   ·   Pomyłki: 0",
            text_color=COLORS["muted"],
        )
        self.live_score.pack(pady=(0, 14))

        opponents = ctk.CTkFrame(
            self.match_view, fg_color=COLORS["surface"], corner_radius=14,
        )
        opponents.grid(row=2, column=1, sticky="nsew", padx=(8, 16), pady=(0, 16))
        ctk.CTkLabel(
            opponents, text="Uczestnicy", anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=14, pady=(13, 6))
        self.opponents_text = ctk.CTkLabel(
            opponents, text="Oczekiwanie na innych prawdziwych graczy…",
            anchor="nw", justify="left", wraplength=260,
            text_color=COLORS["muted"],
        )
        self.opponents_text.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.match_status = ctk.CTkLabel(
            self.match_view, text="", anchor="w", text_color=COLORS["muted"],
        )
        self.match_status.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 10))

    def _build_result_view(self) -> None:
        self.result_title = ctk.CTkLabel(
            self.result_view, text="Wynik pojedynku", anchor="w",
            font=ctk.CTkFont(size=24, weight="bold"), text_color=COLORS["text"],
        )
        self.result_title.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 8))
        self.result_summary = ctk.CTkLabel(
            self.result_view, text="", anchor="w", justify="left",
            wraplength=820, text_color=COLORS["muted"],
        )
        self.result_summary.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        self.result_standings = ctk.CTkScrollableFrame(
            self.result_view, fg_color=COLORS["surface"], corner_radius=12,
        )
        self.result_standings.grid(row=2, column=0, sticky="nsew", padx=18, pady=5)
        actions = ctk.CTkFrame(self.result_view, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=18, pady=14)
        ctk.CTkButton(
            actions, text="Ponowny pojedynek", command=self._request_rematch,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions, text="Ekran główny", command=self._show_overview,
            fg_color=COLORS["surface"], hover_color=COLORS["card_hover"],
        ).pack(side="left", padx=8)

    def _category_changed(self, category: str) -> None:
        self._render_topics(category)

    def _render_topics(self, category: str) -> None:
        for child in self.topic_checks.winfo_children():
            child.destroy()
        self.topic_vars: dict[str, tk.BooleanVar] = {}
        for topic in TOPIC_CATEGORIES[category]:
            variable = tk.BooleanVar(value=True)
            self.topic_vars[topic.value] = variable
            ctk.CTkCheckBox(
                self.topic_checks, text=topic.value.replace("_", " ").capitalize(),
                variable=variable, text_color=COLORS["text"],
            ).pack(anchor="w", padx=8, pady=3)

    @staticmethod
    def _card(
        parent: ctk.CTkFrame, *, row: int, column: int, colspan: int = 1
    ) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent, fg_color=COLORS["card"], corner_radius=15,
            border_color=COLORS["border"], border_width=1,
        )
        card.grid(row=row, column=column, columnspan=colspan, sticky="nsew", padx=5, pady=5)
        return card

    def _collect_settings(self) -> dict[str, object]:
        mode = _MODE_LABELS[self.mode_menu.get()]
        topics = [topic for topic, variable in self.topic_vars.items() if variable.get()]
        if not topics:
            raise ValueError("Zaznacz co najmniej jeden temat.")
        return {
            "mode": mode,
            "duration_seconds": int(self.duration_menu.get()) if mode == "race" else 0,
            "player_count": int(self.players_menu.get()),
            "category": self.category_menu.get(),
            "topics": topics,
            "difficulty": next(
                level for level, label in DIFFICULTY_NAMES.items()
                if label == self.difficulty_menu.get()
            ),
        }

    def _mode_changed(self, mode_label: str) -> None:
        self.duration_menu.configure(
            state="normal" if _MODE_LABELS[mode_label] == "race" else "disabled"
        )

    def _connect(self, pending_action: Callable[[], None] | None = None) -> None:
        url = self.url_entry.get().strip()
        token = self.token_entry.get()
        self._pending_action = pending_action
        try:
            if (
                self.service.authenticated
                and self.service.uses_connection(url, token)
            ):
                if pending_action is None:
                    self._request_leaderboard()
                else:
                    self._perform_pending_action()
                return
            self.service.connect(
                url=url,
                token=token,
                user_id=self.user_id,
                display_name=self.display_name,
                listener=self._queue_server_event,
            )
            self._set_status("Łączenie i uwierzytelnianie na serwerze…")
            self.connection_status.configure(
                text="● Łączenie…", text_color=COLORS["accent"]
            )
        except QuizBattleConnectionError as error:
            self._set_status(str(error), error=True)

    def _quick_game(self) -> None:
        try:
            settings = self._collect_settings()
            self._connect(
                lambda selected=settings: self._start_quick_match(selected)
            )
        except (ValueError, KeyError) as error:
            self._set_status(str(error), error=True)

    def _create_room(self) -> None:
        try:
            settings = self._collect_settings()
            self._connect(
                lambda selected=settings: self._start_friend_room(selected)
            )
        except (ValueError, KeyError) as error:
            self._set_status(str(error), error=True)

    def _join_room(self) -> None:
        code = self.room_entry.get().strip()
        if not code:
            self._set_status("Wpisz kod pokoju.", error=True)
            return
        self._connect(lambda room=code: self._start_join_room(room))

    def _start_quick_match(self, settings: dict[str, object]) -> None:
        self.service.quick_match(settings)
        self._show_match()
        self._set_status("Szukam prawdziwych graczy. Nie dodaję botów.")

    def _start_friend_room(self, settings: dict[str, object]) -> None:
        self.service.create_friend_room(settings)
        self._show_match()
        self._set_status("Tworzę pokój; udostępnij znajomym otrzymany kod.")

    def _start_join_room(self, room_code: str) -> None:
        self.service.join_room(room_code)
        self._show_match()
        self._set_status("Dołączanie do pokoju…")

    def _perform_pending_action(self) -> None:
        pending, self._pending_action = self._pending_action, None
        try:
            if pending is None:
                self._request_leaderboard()
            else:
                pending()
        except (ValueError, RuntimeError, QuizBattleConnectionError) as error:
            self._set_status(str(error), error=True)

    def _submit_answer(self) -> None:
        if not self._current_question_id:
            self._set_status("Poczekaj na pytanie od serwera.", error=True)
            return
        try:
            self.service.submit_answer(
                self._current_question_id, self.answer_entry.get()
            )
            self.answer_button.configure(state="disabled")
            self._current_question_id = ""
            self._set_status("Odpowiedź wysłana do serwera.")
        except (ValueError, RuntimeError, QuizBattleConnectionError) as error:
            self._set_status(str(error), error=True)

    def _leave_match(self) -> None:
        try:
            self.service.leave_match()
            self._show_overview()
            self._set_status("Opuszczono oczekiwanie/mecz.")
        except (RuntimeError, QuizBattleConnectionError) as error:
            self._set_status(str(error), error=True)

    def _request_leaderboard(self) -> None:
        if not self.service.authenticated:
            self.ranking_text.configure(
                text="Ranking online wymaga połączenia z serwerem Quiz Battle."
            )
            return
        try:
            self.service.request_leaderboard(
                _RANKING_SORTS[self.leaderboard_sort.get()]
            )
            self.ranking_text.configure(text="Pobieram ranking z serwera…")
        except (ValueError, RuntimeError, QuizBattleConnectionError) as error:
            self.ranking_text.configure(text=str(error))

    def _request_rematch(self) -> None:
        if not self.service.authenticated or not self._last_battle_id:
            self._set_status("Połącz się z serwerem, aby zaproponować rewanż.")
            return
        try:
            self.service.client.send("rematch_request", battle_id=self._last_battle_id)
            self._show_match()
            self._set_status("Wysłano prośbę o rewanż uczestnikom pojedynku.")
        except (RuntimeError, QuizBattleConnectionError) as error:
            self._set_status(str(error), error=True)

    def _queue_server_event(self, message: dict[str, object]) -> None:
        if self._disposed:
            return
        try:
            self.after(0, lambda event=message: self._handle_server_event(event))
        except tk.TclError:
            return

    def _handle_server_event(self, message: dict[str, object]) -> None:
        event_type = message.get("type")
        if event_type == "connection":
            status = message.get("status")
            if status == "connected":
                self.connection_status.configure(
                    text="● Połączono · uwierzytelnianie…", text_color=COLORS["accent"]
                )
            elif status == "reconnecting":
                self.connection_status.configure(
                    text="● Ponowne łączenie…", text_color=COLORS["accent"]
                )
            else:
                self.connection_status.configure(
                    text="● Błąd połączenia", text_color=COLORS["error"]
                )
            if message.get("message"):
                self._set_status(str(message["message"]), error=status == "error")
        elif event_type == "authenticated":
            self.connection_status.configure(
                text="● Połączono", text_color=COLORS["success"]
            )
            self._set_status(f"Zalogowano do Quiz Battle jako {message.get('display_name', self.display_name)}.")
            self._perform_pending_action()
        elif event_type in {"client_error", "error", "result_rejected"}:
            self._set_status(str(message.get("message", "Serwer zgłosił błąd.")), error=True)
            if event_type == "result_rejected":
                self.result_title.configure(text="Wynik niezweryfikowany")
                self.result_summary.configure(text=str(message.get("message", "")))
                self._show_result()
        elif event_type in {"waiting", "matchmaking_status"}:
            queue_id = message.get("queue_id")
            if isinstance(queue_id, str) and queue_id:
                self.service.set_resume(queue_id=queue_id)
            self._show_match()
            self._set_status(str(message.get("message", "Oczekiwanie na prawdziwych graczy…")))
            self._update_players(message.get("players"))
        elif event_type == "room_created":
            room_code = message.get("room_code")
            if isinstance(room_code, str):
                self._active_room_code = room_code
                self.service.set_resume(room_code=room_code)
                self._set_status(f"Pokój {room_code} utworzony. Skopiuj kod i zaproś znajomych.")
                self.match_title.configure(text=f"Pokój: {room_code}")
                self.clipboard_clear()
                self.clipboard_append(room_code)
            self._show_match()
            self._update_players(message.get("players"))
        elif event_type in {"room_joined", "players_updated"}:
            self._show_match()
            self._update_players(message.get("players"))
            self._set_status(str(message.get("message", "Zaktualizowano uczestników.")))
        elif event_type == "match_started":
            match_id = message.get("match_id")
            if isinstance(match_id, str):
                self._active_match_id = match_id
                self.service.set_resume(
                    match_id=match_id, room_code=self._active_room_code
                )
            mode = message.get("mode")
            self.match_title.configure(
                text=f"Rozgrywka · {_MODE_TITLES.get(str(mode), 'Quiz Battle')}"
            )
            self._show_match()
            self._update_players(message.get("players"))
            if isinstance(message.get("question"), dict):
                self._show_question(message["question"])
            self._set_status("Mecz rozpoczęty przez serwer.")
        elif event_type == "question":
            self._show_question(message)
        elif event_type == "answer_result":
            self.live_score.configure(
                text=(
                    f"Punkty: {message.get('points', 0)}   ·   "
                    f"Pomyłki: {message.get('mistakes', 0)}   ·   "
                    f"Poprawne: {message.get('correct_answers', 0)}"
                )
            )
            self.match_progress.set(self._progress_value(message))
            self._set_status(
                "Poprawna odpowiedź." if message.get("correct") is True
                else "Błędna odpowiedź; wynik zatwierdza serwer.",
                error=message.get("correct") is False,
            )
            self._update_players(message.get("players"))
        elif event_type in {"player_update", "match_status"}:
            self._update_players(message.get("players"))
            self._update_timer(message.get("remaining_seconds"))
            self.match_progress.set(self._progress_value(message))
        elif event_type == "match_finished":
            result = message.get("verified_result")
            if isinstance(result, dict):
                self._render_verified_result(result)
                self._last_battle_id = str(result["battle_id"])
                self._active_match_id = ""
                self._active_room_code = ""
                self.service.set_resume()
                self._refresh_local_data()
            else:
                self._set_status(
                    "Serwer nie dostarczył zweryfikowanego wyniku.", error=True
                )
        elif event_type == "leaderboard":
            self._render_leaderboard(message.get("entries"))
        elif event_type == "rematch_offer":
            self._set_status("Przeciwnicy zaproponowali rewanż.")
        elif event_type == "match_left":
            self._active_match_id = ""
            self._active_room_code = ""
            self.service.set_resume()
            self._show_overview()
        elif event_type == "pong":
            return

    def _show_question(self, question: dict[str, object]) -> None:
        question_id = question.get("question_id")
        prompt = question.get("prompt")
        if not isinstance(question_id, str) or not isinstance(prompt, str):
            self._set_status("Serwer wysłał nieprawidłowe pytanie.", error=True)
            return
        self._current_question_id = question_id
        self.question_label.configure(text=prompt)
        self.answer_entry.delete(0, "end")
        self.answer_button.configure(state="normal")
        self.match_progress.set(self._progress_value(question))
        self._update_timer(question.get("remaining_seconds"))
        self.match_view.grid_rowconfigure(2, weight=1)

    @staticmethod
    def _progress_value(message: dict[str, object]) -> float:
        current = message.get("question_number")
        total = message.get("question_count")
        if (
            isinstance(current, int) and not isinstance(current, bool)
            and isinstance(total, int) and not isinstance(total, bool) and total > 0
        ):
            return max(0.0, min(1.0, current / total))
        return 0.0

    def _update_timer(self, remaining: object) -> None:
        if isinstance(remaining, (int, float)) and not isinstance(remaining, bool):
            self.match_timer.configure(text=f"{max(0, int(remaining))} s")

    def _update_players(self, players: object) -> None:
        if not isinstance(players, list):
            return
        visible: list[str] = []
        for player in players[:8]:
            if not isinstance(player, dict):
                continue
            name = player.get("display_name")
            if not isinstance(name, str) or not name.strip():
                continue
            state = str(player.get("status", "aktywny"))
            points = player.get("points", 0)
            mistakes = player.get("mistakes", 0)
            position = player.get("place")
            prefix = f"#{position} " if isinstance(position, int) else ""
            visible.append(
                f"{prefix}{name.strip()} · {state} · {points} pkt · {mistakes} pomyłek"
            )
        self.opponents_text.configure(
            text="\n".join(visible) if visible
            else "Oczekiwanie na innych prawdziwych graczy…"
        )

    def _render_verified_result(self, result: dict[str, object]) -> None:
        standings = result.get("standings")
        if not isinstance(standings, list):
            self._set_status("Zweryfikowany wynik nie zawiera zestawienia.", error=True)
            return
        self.result_title.configure(
            text="Zwycięstwo!" if result.get("outcome") == "win" else "Pojedynek zakończony"
        )
        summary = (
            f"Miejsce: {result.get('place')}/{result.get('player_count')}   ·   "
            f"Punkty: {result.get('points')}   ·   "
            f"Poprawne: {result.get('correct_answers')}   ·   "
            f"Błędy: {result.get('mistakes')}   ·   "
            f"XP: +{result.get('xp_awarded')}\n"
            f"Tryb: {_MODE_TITLES.get(str(result.get('mode')), str(result.get('mode')))}   ·   "
            f"Czas: {result.get('duration_seconds')} s   ·   "
            f"Pokój: {result.get('room_code') or 'szybka gra'}"
        )
        achievements = result.get("achievements")
        if isinstance(achievements, list) and achievements:
            summary += "\nOsiągnięcia: " + ", ".join(
                str(item.get("title", item.get("key", "")))
                for item in achievements if isinstance(item, dict)
            )
        self.result_summary.configure(text=summary)
        for child in self.result_standings.winfo_children():
            child.destroy()
        winner = next(
            (entry for entry in standings if isinstance(entry, dict) and entry.get("place") == 1),
            None,
        )
        if winner is not None:
            ctk.CTkLabel(
                self.result_standings,
                text=f"Zwycięzca: {winner.get('display_name', '—')}",
                font=ctk.CTkFont(size=17, weight="bold"),
                text_color=COLORS["accent"],
            ).pack(anchor="w", padx=12, pady=(10, 5))
        for entry in standings:
            if not isinstance(entry, dict):
                continue
            status = " · wyeliminowany" if entry.get("eliminated") else ""
            ctk.CTkLabel(
                self.result_standings,
                text=(
                    f"#{entry.get('place')}  {entry.get('display_name')}  ·  "
                    f"{entry.get('points')} pkt  ·  {entry.get('correct_answers')} poprawnych  ·  "
                    f"{entry.get('mistakes')} błędów{status}"
                ),
                anchor="w", text_color=COLORS["text"],
            ).pack(fill="x", padx=12, pady=5)
        self._show_result()

    def _render_leaderboard(self, entries: object) -> None:
        if not isinstance(entries, list):
            self.ranking_text.configure(text="Serwer zwrócił nieprawidłowy ranking.")
            return
        if not entries:
            self.ranking_text.configure(text="Serwer nie zwrócił jeszcze wyników rankingu.")
            return
        lines: list[str] = []
        for entry in entries[:100]:
            if not isinstance(entry, dict):
                continue
            name = entry.get("display_name")
            rank = entry.get("place")
            wins = entry.get("wins")
            points = entry.get("points")
            if not isinstance(name, str) or not isinstance(rank, int):
                continue
            lines.append(f"#{rank}  {name}  ·  {wins} zwycięstw  ·  {points} pkt")
        self.ranking_text.configure(
            text="\n".join(lines) if lines else "Brak poprawnych wpisów w rankingu."
        )

    def _refresh_local_data(self) -> None:
        try:
            stats = self.service.get_stats(self.user_id)
            self.stats_text.configure(
                text=(
                    f"Pojedynki: {stats.matches}   ·   Wygrane: {stats.wins}   ·   "
                    f"Przegrane: {stats.losses}   ·   Skuteczność wygranych: {stats.win_rate:.1f}%\n"
                    f"Punkty łącznie: {stats.points}   ·   Poprawne odpowiedzi: "
                    f"{stats.correct_answers}   ·   Pomyłki: {stats.mistakes}\n"
                    f"Seria wygranych: {stats.current_win_streak}   ·   "
                    f"Najlepsza seria: {stats.best_win_streak}"
                )
            )
            history = self.service.get_history(self.user_id, limit=8)
            self.history_text.configure(
                text="\n".join(self._history_line(item) for item in history)
                if history else "Brak zapisanych, zweryfikowanych pojedynków."
            )
        except (RuntimeError, ValueError) as error:
            self._set_status(str(error), error=True)

    @staticmethod
    def _history_line(item: BattleHistoryItem) -> str:
        outcome = "Wygrana" if item.outcome == "win" else f"Miejsce {item.place}/{item.player_count}"
        return (
            f"{item.completed_at[:16]} · {outcome} · {item.points} pkt · "
            f"{item.correct_answers} poprawnych · {item.mistakes} błędów · +{item.xp_awarded} XP"
        )

    def _show_match(self) -> None:
        self.overview.grid_remove()
        self.result_view.grid_remove()
        self.match_view.grid()

    def _show_result(self) -> None:
        self.overview.grid_remove()
        self.match_view.grid_remove()
        self.result_view.grid()

    def _show_overview(self) -> None:
        self.match_view.grid_remove()
        self.result_view.grid_remove()
        self.overview.grid()
        self._refresh_local_data()

    def _set_status(self, message: str, *, error: bool = False) -> None:
        self.status_label.configure(
            text=message,
            text_color="#FCA5A5" if error else COLORS["muted"],
        )
        self.match_status.configure(
            text=message,
            text_color="#FCA5A5" if error else COLORS["muted"],
        )

    def destroy(self) -> None:
        self._disposed = True
        self.service.set_listener(None)
        super().destroy()
