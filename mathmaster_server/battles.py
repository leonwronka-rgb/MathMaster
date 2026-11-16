from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import WebSocket
from sqlalchemy import select

from mathmaster_server.config import Settings
from mathmaster_server.achievements import unlock_eligible_achievements
from mathmaster_server.matchmaking import MatchmakingQueue
from mathmaster_server.models import Battle, BattleParticipant, Player
from mathmaster_server.questions import Question, SUPPORTED_TOPICS, answers_equal, generate_question
from mathmaster_server.rooms import PlayerConnection, PlayerState, RoomState, new_room_code
from mathmaster_server.scoring import calculate_rating_changes
from mathmaster_server.schemas import MatchSettings

logger = logging.getLogger(__name__)
DIFFICULTY_NAMES = {1: "easy", 2: "easy", 3: "medium", 4: "hard", 5: "expert"}
SUPPORTED_CATEGORY_TOPICS = {
    "Arytmetyka": {"addition", "subtraction", "multiplication", "division", "order_of_operations"},
    "Ułamki": {"fraction_simplify", "fraction_expand", "fraction_addition", "fraction_subtraction", "fraction_multiplication", "fraction_division"},
    "Procenty": {"percent_of", "percent_increase", "percent_decrease", "percent_original"},
    "Algebra": {"algebra_expression", "linear_equation", "linear_inequality", "linear_system", "quadratic_equation"},
    "Geometria": {"area", "perimeter", "volume", "surface_area", "pythagorean", "analytic_geometry"},
    "Potęgi i pierwiastki": {"powers", "square_roots"},
    "Funkcje i wykresy": {"function_value", "graph_point", "sequences"},
    "Trygonometria": {"trigonometry"},
    "Logarytmy": {"logarithms"},
    "Kombinatoryka i prawdopodobieństwo": {"combinatorics", "probability"},
    "Statystyka i dane": {"statistics"},
    "Analiza matematyczna": {"limits", "derivatives", "integrals"},
}


@dataclass(slots=True)
class MatchState:
    match_id: str
    settings: MatchSettings
    players: dict[str, PlayerState]
    room_code: str = ""
    started_at: float = field(default_factory=time.monotonic)
    started_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    question_number: int = 0
    current_question: Question | None = None
    question_started_at: float = field(default_factory=time.monotonic)
    answers: dict[str, tuple[bool, str]] = field(default_factory=dict)
    finish_messages: dict[str, dict[str, Any]] = field(default_factory=dict)
    finished: bool = False
    finished_at: float | None = None
    timer_task: asyncio.Task | None = None
    question_task: asyncio.Task | None = None


class BattleManager:
    """Single-process authoritative queue, rooms, and live match coordinator."""

    def __init__(self, *, session_factory, settings: Settings) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.queue = MatchmakingQueue()
        self.connections: dict[str, PlayerConnection] = {}
        self.rooms: dict[str, RoomState] = {}
        self.matches: dict[str, MatchState] = {}
        self.player_matches: dict[str, str] = {}
        self.last_matches: dict[str, str] = {}
        self._disconnect_tasks: dict[str, asyncio.Task] = {}
        self._matchmaking_task: asyncio.Task | None = None
        self.private_key = Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(settings.result_signing_private_key, validate=True)
        )

    def public_key(self) -> str:
        raw = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode("ascii")

    def start(self) -> None:
        self._matchmaking_task = asyncio.create_task(self._run_matchmaking())

    async def shutdown(self) -> None:
        tasks = [task for task in self._disconnect_tasks.values() if not task.done()]
        if self._matchmaking_task is not None:
            self._matchmaking_task.cancel()
            tasks.append(self._matchmaking_task)
        for match in self.matches.values():
            for task in (match.timer_task, match.question_task):
                if task is not None and not task.done():
                    task.cancel()
                    tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_matchmaking(self) -> None:
        try:
            while True:
                await asyncio.sleep(1)
                seen: set[str] = set()
                for ticket in sorted(
                    tuple(self.queue.tickets.values()), key=lambda item: item.created_at
                ):
                    if ticket.player_id in seen:
                        continue
                    group = self.queue.group_for(ticket, set(self.connections))
                    if not group:
                        continue
                    seen.update(item.player_id for item in group)
                    settings = ticket.settings
                    for item in group:
                        self.queue.remove(item.player_id)
                    await self._start_match(
                        settings,
                        {
                            item.player_id: PlayerState(item.player_id, item.nickname)
                            for item in group
                        },
                    )
                now = time.monotonic()
                for match_id, match in tuple(self.matches.items()):
                    if (
                        match.finished
                        and match.finished_at is not None
                        and now - match.finished_at > 1800
                    ):
                        self.matches.pop(match_id, None)
        except asyncio.CancelledError:
            return

    async def connect(self, player: Player, socket: WebSocket) -> None:
        old = self.connections.get(player.id)
        if old is not None and old.websocket is not socket:
            try:
                await old.send({"type": "connection_replaced"})
                await old.websocket.close(code=4001, reason="Reconnected from another session")
            except Exception:
                pass
        self.connections[player.id] = PlayerConnection(player.id, player.nickname, socket)
        task = self._disconnect_tasks.pop(player.id, None)
        if task is not None:
            task.cancel()

    async def disconnect(self, player_id: str, socket: WebSocket) -> None:
        connection = self.connections.get(player_id)
        if connection is None or connection.websocket is not socket:
            return
        self.connections.pop(player_id, None)
        match_id = self.player_matches.get(player_id)
        if match_id and match_id in self.matches:
            state = self.matches[match_id].players.get(player_id)
            if state is not None:
                state.disconnected_at = time.monotonic()
            task = asyncio.create_task(self._expire_disconnected(player_id, match_id))
            self._disconnect_tasks[player_id] = task
        elif player_id in self.queue.tickets:
            task = asyncio.create_task(self._expire_queue_ticket(player_id))
            self._disconnect_tasks[player_id] = task
        elif any(
            room.match_id is None and player_id in room.players
            for room in self.rooms.values()
        ):
            task = asyncio.create_task(self._expire_waiting_room_player(player_id))
            self._disconnect_tasks[player_id] = task

    async def _expire_queue_ticket(self, player_id: str) -> None:
        try:
            await asyncio.sleep(self.settings.reconnect_grace_seconds)
            if player_id not in self.connections:
                self.queue.remove(player_id)
        except asyncio.CancelledError:
            return
        finally:
            self._disconnect_tasks.pop(player_id, None)

    async def _expire_waiting_room_player(self, player_id: str) -> None:
        try:
            await asyncio.sleep(self.settings.reconnect_grace_seconds)
            if player_id in self.connections:
                return
            for code, room in list(self.rooms.items()):
                if room.match_id is None and player_id in room.players:
                    room.players.pop(player_id)
                    if not room.players:
                        self.rooms.pop(code, None)
                    else:
                        if room.owner_id == player_id:
                            room.owner_id = next(iter(room.players))
                        await self._broadcast_room(room, {
                            "type": "players_updated",
                            "players": self._room_players(room),
                        })
        except asyncio.CancelledError:
            return
        finally:
            self._disconnect_tasks.pop(player_id, None)

    async def _expire_disconnected(self, player_id: str, match_id: str) -> None:
        try:
            await asyncio.sleep(self.settings.reconnect_grace_seconds)
            match = self.matches.get(match_id)
            state = match.players.get(player_id) if match else None
            if state is not None and state.disconnected_at is not None and not match.finished:
                state.eliminated = True
                await self._broadcast_players(match)
                await self._finish_if_decided(match)
        except asyncio.CancelledError:
            return
        finally:
            self._disconnect_tasks.pop(player_id, None)

    async def resume(self, player_id: str, payload: dict[str, Any]) -> None:
        if "queue_id" in payload:
            ticket = self.queue.tickets.get(player_id)
            if ticket and ticket.queue_id == payload["queue_id"]:
                await self._send(player_id, {
                    "type": "waiting", "queue_id": ticket.queue_id, "position": 1,
                })
                return
        match_id = str(
            payload.get("match_id")
            or self.player_matches.get(player_id)
            or self.last_matches.get(player_id)
            or ""
        )
        match = self.matches.get(match_id)
        if match and player_id in match.players and match.finished:
            result = match.finish_messages.get(player_id)
            if result is not None:
                await self._send(player_id, result)
            await self._send(player_id, {
                "type": "match_status",
                "status": "finished",
                "remaining_seconds": 0,
                "players": self._players_public(match),
            })
            return
        if match and player_id in match.players and not match.finished:
            match.players[player_id].disconnected_at = None
            await self._send(
                player_id,
                {
                    "type": "match_started",
                    "match_id": match.match_id,
                    "mode": match.settings.mode,
                    "question": self._question_public(match),
                    "players": self._players_public(match),
                },
            )
            await self._broadcast_players(match)
            return
        if "room_code" in payload:
            room = self.rooms.get(str(payload["room_code"]).upper())
            if room and player_id in room.players and room.match_id is None:
                await self._send_room_state(room)
                if (
                    len(room.players) >= room.settings.player_count
                    and all(identity in self.connections for identity in room.players)
                ):
                    await self._start_room(room)
                return
        await self._send(player_id, {"type": "resume_unavailable"})

    async def handle(self, player: Player, message: dict[str, Any]) -> None:
        kind = message["type"]
        if kind == "matchmaking_join":
            if player.id in self.player_matches or self._in_waiting_room(player.id):
                raise ValueError("Leave the current room or match before entering matchmaking.")
            settings = self._settings(message.get("settings"))
            ticket = self.queue.add(player.id, player.nickname, settings, player.rating)
            await self._send(player.id, {"type": "waiting", "queue_id": ticket.queue_id, "position": len(self.queue.tickets)})
            group = self.queue.group_for(ticket, set(self.connections))
            if group:
                for member in group:
                    self.queue.remove(member.player_id)
                await self._start_match(
                    settings,
                    {
                        item.player_id: PlayerState(item.player_id, item.nickname)
                        for item in group
                    },
                )
        elif kind == "matchmaking_cancel":
            ticket = self.queue.remove(player.id)
            await self._send(player.id, {"type": "matchmaking_cancelled", "queue_id": ticket.queue_id if ticket else ""})
        elif kind == "room_create":
            settings = self._settings(message.get("settings"))
            if player.id in self.player_matches or player.id in self.queue.tickets or self._in_waiting_room(player.id):
                raise ValueError("Leave the current queue or match before creating a room.")
            code = new_room_code(set(self.rooms))
            room = RoomState(code, player.id, settings)
            room.players[player.id] = PlayerState(player.id, player.nickname)
            self.rooms[code] = room
            await self._send(player.id, {
                "type": "room_created", "room_code": code, "players": self._room_players(room),
            })
        elif kind == "room_join":
            code = message["room_code"].upper()
            room = self.rooms.get(code)
            if room is None or room.match_id is not None:
                raise ValueError("Room not found or the match has already started.")
            if player.id in room.players:
                await self._send_room_state(room)
                return
            if len(room.players) >= room.settings.player_count:
                raise ValueError("Room is full.")
            if player.id in self.player_matches or player.id in self.queue.tickets or self._in_waiting_room(player.id):
                raise ValueError("Leave the current queue or match before joining a room.")
            room.players[player.id] = PlayerState(player.id, player.nickname)
            await self._send_room_state(room)
            await self._broadcast_room(room, {"type": "players_updated", "players": self._room_players(room)})
            if (
                len(room.players) == room.settings.player_count
                and all(identity in self.connections for identity in room.players)
            ):
                await self._start_room(room)
        elif kind == "room_start":
            room = self.rooms.get(str(message.get("room_code", "")).upper())
            if room is None or room.owner_id != player.id:
                raise ValueError("Only the room owner can start this room.")
            if len(room.players) < 2:
                raise ValueError("A match requires at least two real players.")
            await self._start_room(room)
        elif kind == "answer_submit":
            await self._answer(player.id, message["question_id"], message["answer"])
        elif kind == "resume":
            await self.resume(player.id, message)
        elif kind == "match_leave":
            await self._leave(player.id)
        elif kind == "leaderboard_request":
            await self._send_leaderboard(player.id, message.get("sort_by", "wins"), message.get("limit", 100))
        elif kind == "rematch_request":
            match_id = self.player_matches.get(player.id) or self.last_matches.get(player.id)
            previous = self.matches.get(match_id or "")
            if previous is None or not previous.finished:
                raise ValueError("No completed match is available for a rematch.")
            players = {
                identity: PlayerState(identity, state.nickname)
                for identity, state in previous.players.items()
                if identity in self.connections
            }
            if len(players) < 2:
                raise ValueError("At least two previous participants must be online.")
            await self._start_match(previous.settings, players)
        else:
            raise ValueError("Unsupported message type.")

    def _in_waiting_room(self, player_id: str) -> bool:
        return any(room.match_id is None and player_id in room.players for room in self.rooms.values())

    async def _start_room(self, room: RoomState) -> None:
        if len(room.players) < 2:
            raise ValueError("A match requires at least two real players.")
        if any(identity not in self.connections for identity in room.players):
            raise ValueError("All room participants must be connected before the match starts.")
        if room.match_id:
            return
        room.match_id = str(uuid.uuid4())
        await self._start_match(room.settings, room.players.copy(), room_code=room.code, match_id=room.match_id)

    async def _start_match(
        self,
        settings: MatchSettings,
        players: dict[str, PlayerState],
        *,
        room_code: str = "",
        match_id: str | None = None,
    ) -> None:
        if len(players) < 2 or len(players) > 8:
            raise ValueError("A match must contain between 2 and 8 real players.")
        match = MatchState(match_id or str(uuid.uuid4()), settings, players, room_code)
        self.matches[match.match_id] = match
        for player_id in players:
            self.player_matches[player_id] = match.match_id
        await self._new_question(match)
        match.timer_task = asyncio.create_task(self._run_timer(match))
        await self._broadcast(
            match,
            {
                "type": "match_started",
                "match_id": match.match_id,
                "mode": settings.mode,
                "question": self._question_public(match),
                "players": self._players_public(match),
            },
        )

    async def _run_timer(self, match: MatchState) -> None:
        try:
            while not match.finished:
                await asyncio.sleep(1)
                if match.settings.mode == "race":
                    remaining = max(0, match.settings.duration_seconds - int(time.monotonic() - match.started_at))
                    await self._broadcast(match, {
                        "type": "match_status",
                        "status": "active",
                        "remaining_seconds": remaining,
                        "players": self._players_public(match),
                    })
                    if remaining <= 0:
                        await self._finish_match(match)
                        return
        except asyncio.CancelledError:
            return

    async def _new_question(self, match: MatchState) -> None:
        if match.finished:
            return
        active = [state for state in match.players.values() if not state.eliminated]
        if len(active) <= 1:
            await self._finish_match(match)
            return
        match.question_number += 1
        match.answers.clear()
        match.current_question = generate_question(match.settings)
        match.question_started_at = time.monotonic()
        if match.question_task is not None and match.question_task is not asyncio.current_task():
            match.question_task.cancel()
        match.question_task = asyncio.create_task(self._question_timeout(match, match.current_question.question_id))
        await self._broadcast(match, {
            "type": "question",
            **self._question_public(match),
        })

    async def _question_timeout(self, match: MatchState, question_id: str) -> None:
        try:
            await asyncio.sleep(self.settings.battle_question_timeout_seconds)
            if match.finished or match.current_question is None or match.current_question.question_id != question_id:
                return
            for player_id, state in match.players.items():
                if not state.eliminated and player_id not in match.answers:
                    state.mistakes += 1
                    match.answers[player_id] = (False, "")
                    if match.settings.mode == "survival" and state.mistakes >= 3:
                        state.eliminated = True
            await self._reveal_answers(match)
        except asyncio.CancelledError:
            return

    async def _answer(self, player_id: str, question_id: str, answer: str) -> None:
        match = self.matches.get(self.player_matches.get(player_id, ""))
        if match is None or match.finished or match.current_question is None:
            raise ValueError("There is no active question for this player.")
        state = match.players.get(player_id)
        if state is None or state.eliminated:
            raise ValueError("This player is not active in the match.")
        question = match.current_question
        if question.question_id != question_id:
            raise ValueError("The question is stale or does not belong to this match.")
        if player_id in match.answers or question_id in state.answered_questions:
            raise ValueError("An answer for this question was already submitted.")
        state.answered_questions.add(question_id)
        correct = answers_equal(answer, question.answer)
        state.last_answer_at = time.monotonic()
        if correct:
            state.correct_answers += 1
            state.points += 10
        else:
            state.mistakes += 1
            if match.settings.mode == "survival" and state.mistakes >= 3:
                state.eliminated = True
        match.answers[player_id] = (correct, answer)
        await self._broadcast_players(match)
        active_ids = {
            identity for identity, item in match.players.items()
            if not item.eliminated and item.disconnected_at is None
        }
        if active_ids.issubset(match.answers.keys()):
            await self._reveal_answers(match)

    async def _reveal_answers(self, match: MatchState) -> None:
        if match.finished or match.current_question is None:
            return
        question = match.current_question
        if match.question_task is not None and match.question_task is not asyncio.current_task():
            match.question_task.cancel()
        for player_id, state in match.players.items():
            answer = match.answers.get(player_id)
            if answer is None:
                continue
            await self._send(player_id, {
                "type": "answer_result",
                "question_id": question.question_id,
                "correct": answer[0],
                "correct_answer": question.answer,
                "points": state.points,
                "mistakes": state.mistakes,
                "eliminated": state.eliminated,
            })
        await self._broadcast_players(match)
        await self._finish_if_decided(match)
        if not match.finished:
            await self._new_question(match)

    async def _finish_if_decided(self, match: MatchState) -> None:
        active = [
            item for item in match.players.values()
            if not item.eliminated and item.disconnected_at is None
        ]
        if len(active) <= 1:
            await self._finish_match(match)

    async def _leave(self, player_id: str) -> None:
        self.queue.remove(player_id)
        for code, room in list(self.rooms.items()):
            if player_id in room.players and room.match_id is None:
                room.players.pop(player_id, None)
                if not room.players:
                    self.rooms.pop(code, None)
                else:
                    if room.owner_id == player_id:
                        room.owner_id = next(iter(room.players))
                    await self._broadcast_room(room, {
                        "type": "players_updated", "players": self._room_players(room),
                    })
        match = self.matches.get(self.player_matches.get(player_id, ""))
        if match and not match.finished:
            state = match.players.get(player_id)
            if state is not None:
                state.eliminated = True
                state.disconnected_at = None
                await self._broadcast_players(match)
                await self._finish_if_decided(match)
        await self._send(player_id, {"type": "match_left"})

    async def _finish_match(self, match: MatchState) -> None:
        if match.finished:
            return
        match.finished = True
        match.finished_at = time.monotonic()
        for task in (match.timer_task, match.question_task):
            if task is not None and task is not asyncio.current_task():
                task.cancel()
        # A stable server-side tie-break makes every signed result's places unique.
        ordered = sorted(
            match.players.values(),
            key=lambda item: (
                item.eliminated,
                -item.points,
                -item.correct_answers,
                item.mistakes,
                item.last_answer_at or float("inf"),
                item.player_id,
            ),
        )
        places = [index + 1 for index in range(len(ordered))]
        winner = ordered[0] if ordered else None
        ratings = self._ratings([item.player_id for item in ordered])
        rating_changes = calculate_rating_changes(ratings, places) if ordered else []
        completed_at = datetime.now(timezone.utc)
        actual_duration = min(3600, max(0, int(time.monotonic() - match.started_at)))
        participants_payload = []
        for index, state in enumerate(ordered):
            participants_payload.append({
                "player_id": state.player_id,
                "display_name": state.nickname,
                "points": state.points,
                "correct_answers": state.correct_answers,
                "mistakes": state.mistakes,
                "eliminated": state.eliminated,
                "place": places[index],
            })
        if len(ordered) >= 2 and winner is not None:
            try:
                newly_unlocked = self._persist_result(
                    match, ordered, places, rating_changes, completed_at, winner.player_id
                )
            except Exception:
                await self._broadcast(match, {
                    "type": "error",
                    "message": "Wynik nie został zapisany. Nagrody nie zostały przyznane.",
                })
            else:
                for state in ordered:
                    payload = {
                        "battle_id": match.match_id,
                        "player_id": state.player_id,
                        "winner_player_id": winner.player_id,
                        "mode": match.settings.mode,
                        "difficulty": DIFFICULTY_NAMES[match.settings.difficulty],
                        "completed_at": completed_at.isoformat(),
                        "duration_seconds": actual_duration,
                        "room_code": match.room_code,
                        "standings": participants_payload,
                    }
                    serialized = json.dumps(
                        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                    ).encode("utf-8")
                    finish_message = {
                        "type": "match_finished",
                        "signed_payload": base64.b64encode(serialized).decode("ascii"),
                        "signature": base64.b64encode(self.private_key.sign(serialized)).decode("ascii"),
                        "achievements": newly_unlocked.get(state.player_id, []),
                    }
                    match.finish_messages[state.player_id] = finish_message
                    await self._send(state.player_id, finish_message)
        await self._broadcast(match, {
            "type": "match_status",
            "status": "finished",
            "remaining_seconds": 0,
            "players": self._players_public(match),
        })
        for player_id in match.players:
            self.player_matches.pop(player_id, None)
            self.last_matches[player_id] = match.match_id
        if match.room_code:
            self.rooms.pop(match.room_code, None)

    def _persist_result(
        self,
        match: MatchState,
        ordered: list[PlayerState],
        places: list[int],
        rating_changes: list[int],
        completed_at: datetime,
        winner_id: str,
    ) -> dict[str, list[str]]:
        session = self.session_factory()
        newly_unlocked: dict[str, list[str]] = {}
        try:
            battle = Battle(
                id=match.match_id,
                mode=match.settings.mode,
                difficulty=DIFFICULTY_NAMES[match.settings.difficulty],
                category=match.settings.category,
                duration_seconds=int(time.monotonic() - match.started_at),
                room_code=match.room_code,
                completed_at=completed_at,
                winner_player_id=winner_id,
            )
            session.add(battle)
            for index, item in enumerate(ordered):
                player = session.get(Player, item.player_id)
                if player is None:
                    continue
                outcome = "win" if index == 0 else "loss"
                change = rating_changes[index]
                player.matches += 1
                player.wins += int(outcome == "win")
                player.losses += int(outcome == "loss")
                player.draws += int(outcome == "draw")
                player.correct_answers += item.correct_answers
                player.mistakes += item.mistakes
                player.rating = max(100, player.rating + change)
                newly_unlocked[item.player_id] = unlock_eligible_achievements(session, player)
                session.add(BattleParticipant(
                    battle_id=match.match_id,
                    player_id=item.player_id,
                    points=item.points,
                    correct_answers=item.correct_answers,
                    mistakes=item.mistakes,
                    eliminated=item.eliminated,
                    place=places[index],
                    outcome=outcome,
                    rating_change=change,
                ))
            session.commit()
            return newly_unlocked
        except Exception:
            session.rollback()
            logger.exception("Could not persist completed Quiz Battle %s", match.match_id)
            raise
        finally:
            session.close()

    def _ratings(self, player_ids: list[str]) -> list[int]:
        session = self.session_factory()
        try:
            return [
                (session.get(Player, identity).rating if session.get(Player, identity) else 1000)
                for identity in player_ids
            ]
        finally:
            session.close()

    async def _send_leaderboard(self, player_id: str, sort_by: str, limit: int) -> None:
        if sort_by not in {"wins", "points", "win_rate"} or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Invalid leaderboard query.")
        session = self.session_factory()
        try:
            players = session.scalars(select(Player).where(Player.matches > 0)).all()
            def sort_key(player: Player):
                if sort_by == "wins":
                    metric = player.wins
                elif sort_by == "points":
                    metric = player.rating
                else:
                    metric = player.wins / player.matches if player.matches else 0
                return (-metric, -player.rating, player.id)
            players.sort(key=sort_key)
            result = [{
                "rank": index,
                "player_id": player.id,
                "display_name": player.nickname,
                "points": player.rating,
                "wins": player.wins,
                "losses": player.losses,
                "matches": player.matches,
                "win_rate": round(100 * player.wins / player.matches, 1),
            } for index, player in enumerate(players[:limit], 1)]
        finally:
            session.close()
        await self._send(player_id, {"type": "leaderboard", "players": result, "sort_by": sort_by})

    def _settings(self, raw: Any) -> MatchSettings:
        try:
            settings = MatchSettings.model_validate(raw)
        except Exception as error:
            raise ValueError("Invalid match settings.") from error
        category_topics = SUPPORTED_CATEGORY_TOPICS.get(settings.category)
        if category_topics is None or any(
            topic not in SUPPORTED_TOPICS or topic not in category_topics
            for topic in settings.topics
        ):
            raise ValueError("The selected category or topic is not supported by the server question bank.")
        return settings

    async def _send_room_state(self, room: RoomState) -> None:
        await self._send(room.owner_id, {
            "type": "room_created",
            "room_code": room.code,
            "players": self._room_players(room),
        })
        for identity in room.players:
            if identity != room.owner_id:
                await self._send(identity, {
                    "type": "room_joined",
                    "room_code": room.code,
                    "players": self._room_players(room),
                })

    async def _broadcast_room(self, room: RoomState, message: dict[str, Any]) -> None:
        for player_id in tuple(room.players):
            await self._send(player_id, message)

    async def _send(self, player_id: str, message: dict[str, Any]) -> None:
        connection = self.connections.get(player_id)
        if connection is not None:
            try:
                await connection.send(message)
            except Exception:
                logger.debug("WebSocket send failed for player %s", player_id)

    async def _broadcast(self, match: MatchState, message: dict[str, Any]) -> None:
        for player_id in tuple(match.players):
            await self._send(player_id, message)

    async def _broadcast_players(self, match: MatchState) -> None:
        await self._broadcast(match, {
            "type": "players_updated",
            "players": self._players_public(match),
        })

    @staticmethod
    def _room_players(room: RoomState) -> list[dict[str, Any]]:
        return [
            {"player_id": state.player_id, "display_name": state.nickname, "status": "waiting",
             "points": state.points, "mistakes": state.mistakes}
            for state in room.players.values()
        ]

    @staticmethod
    def _players_public(match: MatchState) -> list[dict[str, Any]]:
        return [
            {
                "player_id": state.player_id,
                "display_name": state.nickname,
                "status": "disconnected" if state.disconnected_at is not None else "eliminated" if state.eliminated else "active",
                "points": state.points,
                "mistakes": state.mistakes,
                "correct_answers": state.correct_answers,
            }
            for state in match.players.values()
        ]

    def _question_public(self, match: MatchState) -> dict[str, Any] | None:
        question = match.current_question
        if question is None:
            return None
        remaining = max(
            0,
            int(
                self.settings.battle_question_timeout_seconds
                - (time.monotonic() - match.question_started_at)
            ),
        )
        return question.public(match.question_number, 0, remaining)

