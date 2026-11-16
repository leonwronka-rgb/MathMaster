from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from mathmaster_server.authentication import decode_access_token
from mathmaster_server.models import Player

logger = logging.getLogger(__name__)
router = APIRouter()
MAX_MESSAGE_BYTES = 64_000
MESSAGE_FIELDS = {
    "matchmaking_join": {"type", "settings", "friends_only"},
    "matchmaking_cancel": {"type"},
    "room_create": {"type", "settings", "friends_only"},
    "room_join": {"type", "room_code"},
    "room_start": {"type", "room_code"},
    "answer_submit": {"type", "question_id", "answer"},
    "resume": {"type", "match_id", "room_code", "queue_id"},
    "match_leave": {"type"},
    "leaderboard_request": {"type", "sort_by", "limit"},
    "rematch_request": {"type"},
}


@router.websocket("/v1/ws")
async def quiz_battle_socket(websocket: WebSocket) -> None:
    app = websocket.app
    settings = app.state.settings
    origin = websocket.headers.get("origin")
    allowed_origins = {
        item.strip() for item in settings.cors_origins.split(",") if item.strip()
    }
    if origin and allowed_origins and origin not in allowed_origins:
        await websocket.close(code=1008, reason="Origin is not allowed")
        return
    await websocket.accept()
    manager = app.state.battle_manager
    player: Player | None = None
    try:
        remote = websocket.client.host if websocket.client else "unknown"
        app.state.rate_limiter.check(
            f"{remote}:websocket-connect",
            limit=20,
            window_seconds=settings.rate_limit_window_seconds,
        )
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        auth_message = _parse(raw)
        if (
            set(auth_message) != {"type", "token", "display_name", "protocol_version"}
            or auth_message["type"] != "authenticate"
            or auth_message["protocol_version"] != 1
            or not isinstance(auth_message["token"], str)
            or not isinstance(auth_message["display_name"], str)
            or not auth_message["display_name"].strip()
            or len(auth_message["display_name"]) > 80
        ):
            raise ValueError("Invalid authentication message.")
        player_id = decode_access_token(auth_message["token"], settings)
        session = app.state.session_factory()
        try:
            player = session.scalar(select(Player).where(Player.id == player_id))
            if player is None:
                raise ValueError("Player account no longer exists.")
            # Keep the canonical registered nickname; clients cannot impersonate another display name.
            await manager.connect(player, websocket)
            await websocket.send_json({
                "type": "authenticated",
                "player_id": player.id,
                "display_name": player.nickname,
                "protocol_version": 1,
            })
        finally:
            session.close()
        while True:
            raw = await websocket.receive_text()
            message = _parse(raw)
            app.state.rate_limiter.check(
                f"{player.id}:websocket-message",
                limit=settings.websocket_rate_limit,
                window_seconds=settings.rate_limit_window_seconds,
            )
            try:
                _validate_message(message)
                await manager.handle(player, message)
            except HTTPException as error:
                await manager._send(player.id, {
                    "type": "error",
                    "message": str(error.detail),
                })
                if error.status_code == 429:
                    await websocket.close(code=4429, reason="Rate limit exceeded")
                    return
            except ValueError as error:
                await manager._send(player.id, {"type": "error", "message": str(error)})
    except WebSocketDisconnect:
        pass
    except (ValueError, TimeoutError, asyncio.TimeoutError) as error:
        try:
            await websocket.send_json({"type": "client_error", "message": str(error)})
            await websocket.close(code=4401, reason="Authentication or message validation failed")
        except Exception:
            pass
    except Exception:
        logger.exception("Quiz Battle WebSocket failed")
        try:
            await websocket.send_json({"type": "error", "message": "Server could not process the request."})
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if player is not None:
            await manager.disconnect(player.id, websocket)


def _parse(raw: str) -> dict[str, Any]:
    if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("WebSocket message exceeds the size limit.")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("Invalid JSON WebSocket message.") from error
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise ValueError("Message must be a JSON object with a type.")
    return value


def _validate_message(message: dict[str, Any]) -> None:
    kind = message["type"]
    allowed = MESSAGE_FIELDS.get(kind)
    if allowed is None or not set(message).issubset(allowed):
        raise ValueError("Unsupported message type or unexpected fields.")
    if kind in {"matchmaking_join", "room_create"}:
        if not isinstance(message.get("settings"), dict):
            raise ValueError("Match settings are required.")
        if not isinstance(message.get("friends_only"), bool):
            raise ValueError("friends_only must be a boolean.")
    elif kind == "room_join":
        code = message.get("room_code")
        if not isinstance(code, str) or not 4 <= len(code) <= 16 or not code.isalnum():
            raise ValueError("Invalid room code.")
    elif kind == "room_start":
        if not isinstance(message.get("room_code"), str) or len(message["room_code"]) > 16:
            raise ValueError("Invalid room code.")
    elif kind == "answer_submit":
        question_id, answer = message.get("question_id"), message.get("answer")
        if not isinstance(question_id, str) or not 1 <= len(question_id) <= 120:
            raise ValueError("Invalid question identifier.")
        if not isinstance(answer, str) or len(answer) > 2_000:
            raise ValueError("Answer must be a string of at most 2,000 characters.")
    elif kind == "resume":
        identifiers = {key: value for key, value in message.items() if key != "type"}
        if not identifiers or any(not isinstance(value, str) or not value or len(value) > 120
                                  for value in identifiers.values()):
            raise ValueError("Resume requires a valid queue, room, or match identifier.")
    elif kind == "leaderboard_request":
        sort_by, limit = message.get("sort_by", "wins"), message.get("limit", 100)
        if sort_by not in {"wins", "points", "win_rate"}:
            raise ValueError("Invalid leaderboard sort field.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Leaderboard limit must be between 1 and 100.")

