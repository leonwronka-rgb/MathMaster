from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from urllib.parse import urlparse

import websocket

_MAX_MESSAGE_BYTES = 64_000


class QuizBattleConnectionError(RuntimeError):
    pass


class QuizBattleClient:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self._stop = threading.Event()
        self._send_lock = threading.Lock()
        self._socket: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._authenticated = threading.Event()
        self._listener: Callable[[dict[str, object]], None] | None = None
        self._url = ""
        self._token = ""
        self._display_name = ""
        self._resume: dict[str, str] = {}

    @property
    def authenticated(self) -> bool:
        return self._authenticated.is_set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def uses_connection(self, url: str, token: str) -> bool:
        return self._url == url.strip() and self._token == token

    def connect(
        self,
        url: str,
        token: str,
        display_name: str,
        listener: Callable[[dict[str, object]], None],
    ) -> None:
        parsed = urlparse(url.strip())
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if (
            parsed.scheme not in {"ws", "wss"}
            or not parsed.hostname
            or (parsed.scheme == "ws" and parsed.hostname not in local_hosts)
            or parsed.username is not None
            or parsed.password is not None
            or len(url) > 2_048
        ):
            raise QuizBattleConnectionError(
                "Użyj adresu WSS serwera Quiz Battle; WS jest dozwolone tylko lokalnie."
            )
        if not token.strip() or len(token) > 4_096:
            raise QuizBattleConnectionError("Wpisz ważny token logowania do serwera.")
        if not display_name.strip() or len(display_name) > 80:
            raise QuizBattleConnectionError("Nieprawidłowa nazwa gracza.")
        if self.running:
            if self._url == url.strip() and self._token == token:
                self._listener = listener
                return
            self.close()
        self._stop.clear()
        self._authenticated.clear()
        self._url = url.strip()
        self._token = token
        self._display_name = display_name.strip()
        self._listener = listener
        self._thread = threading.Thread(
            target=self._connection_loop,
            name="mathmaster-quiz-battle",
            daemon=True,
        )
        self._thread.start()

    def set_listener(
        self, listener: Callable[[dict[str, object]], None] | None
    ) -> None:
        self._listener = listener

    def set_resume(
        self, *, match_id: str = "", room_code: str = "", queue_id: str = ""
    ) -> None:
        self._resume = {
            key: value
            for key, value in (
                ("match_id", match_id),
                ("room_code", room_code),
                ("queue_id", queue_id),
            )
            if value
        }

    def send(self, message_type: str, **payload: object) -> None:
        if not self.authenticated:
            raise QuizBattleConnectionError(
                "Połącz się i uwierzytelnij na serwerze przed wykonaniem tej czynności."
            )
        self._send_json({"type": message_type, **payload})

    def close(self) -> None:
        self._stop.set()
        self._authenticated.clear()
        current = self._socket
        if current is not None:
            current.close()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._thread = None

    def _connection_loop(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            socket_app = websocket.WebSocketApp(
                self._url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self._socket = socket_app
            try:
                socket_app.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as error:
                self.logger.warning("Quiz Battle WebSocket stopped: %s", error)
                self._emit({"type": "connection", "status": "error", "message": str(error)})
            self._authenticated.clear()
            self._socket = None
            if self._stop.is_set():
                break
            self._emit({
                "type": "connection",
                "status": "reconnecting",
                "message": "Połączenie przerwane; ponawiam próbę.",
            })
            self._stop.wait(delay)
            delay = min(delay * 2, 30)

    def _on_open(self, socket_app: websocket.WebSocketApp) -> None:
        self._authenticated.clear()
        self._emit({"type": "connection", "status": "connected"})
        self._send_json({
            "type": "authenticate",
            "token": self._token,
            "display_name": self._display_name,
            "protocol_version": 1,
        })

    def _on_message(self, _socket: websocket.WebSocketApp, raw: str) -> None:
        if len(raw.encode("utf-8")) > _MAX_MESSAGE_BYTES:
            self._emit({
                "type": "client_error",
                "message": "Odpowiedź serwera przekracza limit rozmiaru.",
            })
            return
        try:
            message = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as error:
            self._emit({
                "type": "client_error",
                "message": f"Nieprawidłowa odpowiedź serwera: {error}",
            })
            return
        if not isinstance(message, dict) or not isinstance(message.get("type"), str):
            self._emit({
                "type": "client_error",
                "message": "Serwer wysłał wiadomość o nieprawidłowym formacie.",
            })
            return
        if message["type"] == "authenticated":
            player_id = message.get("player_id")
            if not isinstance(player_id, str) or not player_id.strip():
                self._emit({
                    "type": "client_error",
                    "message": "Serwer nie potwierdził tożsamości gracza.",
                })
                return
            self._authenticated.set()
            self._emit(message)
            if self._resume:
                self._send_json({"type": "resume", **self._resume})
            return
        self._emit(message)

    def _on_error(self, _socket: websocket.WebSocketApp, error: object) -> None:
        self._authenticated.clear()
        self._emit({
            "type": "connection",
            "status": "error",
            "message": str(error),
        })

    def _on_close(
        self,
        _socket: websocket.WebSocketApp,
        status_code: int | None,
        reason: str | None,
    ) -> None:
        self._authenticated.clear()
        if not self._stop.is_set():
            self._emit({
                "type": "connection",
                "status": "reconnecting",
                "message": reason or f"Połączenie zamknięte ({status_code}).",
            })

    def _send_json(self, message: dict[str, object]) -> None:
        socket_app = self._socket
        if socket_app is None:
            raise QuizBattleConnectionError("Brak aktywnego połączenia z serwerem.")
        serialized = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self._send_lock:
            socket_app.send(serialized)

    def _emit(self, message: dict[str, object]) -> None:
        listener = self._listener
        if listener is not None:
            listener(message)
