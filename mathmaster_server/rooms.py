from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


@dataclass(slots=True)
class PlayerConnection:
    player_id: str
    nickname: str
    websocket: WebSocket
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, message: dict[str, Any]) -> None:
        async with self.send_lock:
            await self.websocket.send_json(message)


@dataclass(slots=True)
class PlayerState:
    player_id: str
    nickname: str
    points: int = 0
    correct_answers: int = 0
    mistakes: int = 0
    eliminated: bool = False
    disconnected_at: float | None = None
    last_answer_at: float = 0.0
    answered_questions: set[str] = field(default_factory=set)


@dataclass(slots=True)
class RoomState:
    code: str
    owner_id: str
    settings: Any
    players: dict[str, PlayerState] = field(default_factory=dict)
    match_id: str | None = None
    private: bool = True


def new_room_code(existing: set[str]) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(20):
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if code not in existing:
            return code
    raise RuntimeError("Unable to allocate a unique room code.")

