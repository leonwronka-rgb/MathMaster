from __future__ import annotations

import base64
import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from database.database import Database
from gamification.service import GamificationService, VerifiedBattleResult
from mathematics.topics import TOPIC_CATEGORIES
from quiz_battle.client import QuizBattleClient, QuizBattleConnectionError


@dataclass(frozen=True, slots=True)
class BattleHistoryItem:
    battle_id: str
    outcome: str
    mode: str
    difficulty: str
    room_code: str
    points: int
    correct_answers: int
    mistakes: int
    place: int
    player_count: int
    duration_seconds: int
    xp_awarded: int
    completed_at: str
    standings: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class BattleStats:
    matches: int
    wins: int
    losses: int
    win_rate: float
    points: int
    correct_answers: int
    mistakes: int
    current_win_streak: int
    best_win_streak: int


class QuizBattleService:
    def __init__(
        self,
        database: Database,
        gamification: GamificationService,
        on_verified_result: Callable[[], None] | None = None,
    ) -> None:
        self.database = database
        self.gamification = gamification
        self.client = QuizBattleClient()
        self.logger = logging.getLogger(__name__)
        self._user_id: int | None = None
        self._player_id: str | None = None
        self._listener: Callable[[dict[str, object]], None] | None = None
        self._resume: dict[str, str] = {}
        self._on_verified_result = on_verified_result

    @property
    def authenticated(self) -> bool:
        return self.client.authenticated and self._player_id is not None

    @property
    def player_id(self) -> str | None:
        return self._player_id

    def uses_connection(self, url: str, token: str) -> bool:
        return self.client.uses_connection(url, token)

    def connect(
        self,
        *,
        url: str,
        token: str,
        user_id: int,
        display_name: str,
        listener: Callable[[dict[str, object]], None],
    ) -> None:
        self._user_id = user_id
        self._listener = listener
        if self.client.running and self.client.uses_connection(url, token):
            return
        self._player_id = None
        self.client.connect(url, token, display_name, self._on_client_event)

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
        self.client.set_resume(
            match_id=match_id, room_code=room_code, queue_id=queue_id
        )

    def resume_active_match(self) -> None:
        if self.client.authenticated and self._resume:
            self.client.send("resume", **self._resume)

    def quick_match(self, settings: dict[str, object]) -> None:
        self._validate_settings(settings)
        self.client.send("matchmaking_join", settings=settings, friends_only=False)

    def create_friend_room(self, settings: dict[str, object]) -> None:
        self._validate_settings(settings)
        self.client.send("room_create", settings=settings, friends_only=True)

    def join_room(self, room_code: str) -> None:
        code = room_code.strip().upper()
        if not 4 <= len(code) <= 16 or not code.isalnum():
            raise ValueError("Kod pokoju musi zawierać 4–16 liter lub cyfr.")
        self.client.send("room_join", room_code=code)

    def submit_answer(self, question_id: str, answer: str) -> None:
        if not question_id or len(question_id) > 120 or len(answer) > 2_000:
            raise ValueError("Nieprawidłowa odpowiedź lub identyfikator pytania.")
        self.client.send(
            "answer_submit", question_id=question_id, answer=answer.strip()
        )

    def request_leaderboard(self, sort_by: str = "wins") -> None:
        if sort_by not in {"wins", "points", "win_rate"}:
            raise ValueError("Nieznany sposób sortowania rankingu Quiz Battle.")
        self.client.send("leaderboard_request", sort_by=sort_by, limit=100)

    def leave_match(self) -> None:
        if self.authenticated:
            self.client.send("match_leave")
        self.set_resume()

    def close(self) -> None:
        self.client.close()
        self._player_id = None

    def _on_client_event(self, message: dict[str, object]) -> None:
        self._handle_server_message(message)
        listener = self._listener
        if listener is not None:
            listener(message)

    def get_history(
        self, user_id: int, limit: int = 50
    ) -> tuple[BattleHistoryItem, ...]:
        if not 1 <= limit <= 200:
            raise ValueError("Limit historii musi należeć do zakresu 1–200.")
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    """
                    SELECT battle_id, outcome, mode, difficulty, room_code, points,
                           correct_answers, mistakes, place, player_count,
                           duration_seconds, xp_awarded, completed_at, standings_json
                    FROM quiz_battle_results
                    WHERE user_id = ?
                    ORDER BY completed_at DESC, battle_id DESC LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            return tuple(
                BattleHistoryItem(
                    battle_id=str(row["battle_id"]),
                    outcome=str(row["outcome"]),
                    mode=str(row["mode"]),
                    difficulty=str(row["difficulty"]),
                    room_code=str(row["room_code"]),
                    points=int(row["points"]),
                    correct_answers=int(row["correct_answers"]),
                    mistakes=int(row["mistakes"]),
                    place=int(row["place"]),
                    player_count=int(row["player_count"]),
                    duration_seconds=int(row["duration_seconds"]),
                    xp_awarded=int(row["xp_awarded"]),
                    completed_at=str(row["completed_at"]),
                    standings=tuple(json.loads(str(row["standings_json"]))),
                )
                for row in rows
            )
        except sqlite3.Error as error:
            self.logger.exception("Database failure while reading Quiz Battle history")
            raise RuntimeError("Nie udało się wczytać historii pojedynków.") from error

    def get_stats(self, user_id: int) -> BattleStats:
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    """
                    SELECT outcome, points, correct_answers, mistakes
                    FROM quiz_battle_results
                    WHERE user_id = ? ORDER BY completed_at, battle_id
                    """,
                    (user_id,),
                ).fetchall()
            wins = sum(row["outcome"] == "win" for row in rows)
            current_streak = best_streak = 0
            for row in rows:
                current_streak = current_streak + 1 if row["outcome"] == "win" else 0
                best_streak = max(best_streak, current_streak)
            count = len(rows)
            return BattleStats(
                matches=count,
                wins=wins,
                losses=count - wins,
                win_rate=100 * wins / count if count else 0.0,
                points=sum(int(row["points"]) for row in rows),
                correct_answers=sum(int(row["correct_answers"]) for row in rows),
                mistakes=sum(int(row["mistakes"]) for row in rows),
                current_win_streak=current_streak,
                best_win_streak=best_streak,
            )
        except sqlite3.Error as error:
            self.logger.exception("Database failure while reading Quiz Battle stats")
            raise RuntimeError("Nie udało się wczytać statystyk Quiz Battle.") from error

    def _handle_server_message(self, message: dict[str, object]) -> None:
        if message.get("type") == "authenticated":
            player_id = message.get("player_id")
            if isinstance(player_id, str) and player_id.strip():
                self._player_id = player_id
            else:
                message.clear()
                message.update({
                    "type": "client_error",
                    "message": "Serwer zwrócił nieprawidłowy identyfikator gracza.",
                })
            return
        if message.get("type") != "match_finished":
            return
        try:
            if self._user_id is None or self._player_id is None:
                raise ValueError("Nie ma aktywnego uwierzytelnionego gracza.")
            encoded_payload = message.get("signed_payload")
            signature = message.get("signature")
            if not isinstance(encoded_payload, str) or not isinstance(signature, str):
                raise ValueError("Serwer nie dostarczył podpisanego wyniku meczu.")
            signed_payload = base64.b64decode(encoded_payload, validate=True)
            reward = self.gamification.record_verified_battle_result(
                signed_payload,
                signature,
                user_id=self._user_id,
                expected_player_id=self._player_id,
            )
            message["verified_result"] = self._result_payload(reward)
            if self._on_verified_result is not None and not reward.duplicate:
                self._on_verified_result()
        except (ValueError, RuntimeError) as error:
            self.logger.warning("Rejected Quiz Battle result: %s", error)
            message.clear()
            message.update({
                "type": "result_rejected",
                "message": f"Wynik nie został zweryfikowany i nie zapisano nagród: {error}",
            })

    @staticmethod
    def _result_payload(result: VerifiedBattleResult) -> dict[str, object]:
        return {
            "battle_id": result.battle_id,
            "player_id": result.player_id,
            "outcome": result.outcome,
            "mode": result.mode,
            "difficulty": result.difficulty,
            "room_code": result.room_code,
            "points": result.points,
            "correct_answers": result.correct_answers,
            "mistakes": result.mistakes,
            "place": result.place,
            "player_count": result.player_count,
            "duration_seconds": result.duration_seconds,
            "xp_awarded": result.xp_awarded,
            "duplicate": result.duplicate,
            "standings": [
                {
                    "player_id": item.player_id,
                    "display_name": item.display_name,
                    "points": item.points,
                    "correct_answers": item.correct_answers,
                    "mistakes": item.mistakes,
                    "eliminated": item.eliminated,
                    "place": item.place,
                }
                for item in result.standings
            ],
            "achievements": [
                {
                    "key": item.key,
                    "title": item.title,
                    "icon": item.icon,
                    "xp_reward": item.xp_reward,
                }
                for item in result.achievements
            ],
        }

    @staticmethod
    def _validate_settings(settings: dict[str, object]) -> None:
        if set(settings) != {
            "mode", "duration_seconds", "player_count", "category",
            "topics", "difficulty",
        }:
            raise ValueError("Nieprawidłowe ustawienia pojedynku.")
        if not isinstance(settings["mode"], str) or settings["mode"] not in {"race", "survival"}:
            raise ValueError("Wybierz prawidłowy tryb pojedynku.")
        duration = settings["duration_seconds"]
        if (
            isinstance(duration, bool)
            or not isinstance(duration, int)
            or (settings["mode"] == "race" and duration not in {60, 120, 180})
            or (settings["mode"] == "survival" and duration != 0)
        ):
            raise ValueError("Czas wyścigu to 60/120/180 s; tryb eliminacji nie ma limitu czasu.")
        if (
            isinstance(settings["player_count"], bool)
            or not isinstance(settings["player_count"], int)
            or not 2 <= settings["player_count"] <= 8
        ):
            raise ValueError("Pojedynek może mieć od 2 do 8 graczy.")
        category = settings["category"]
        if not isinstance(category, str) or category not in TOPIC_CATEGORIES:
            raise ValueError("Wybierz dział matematyki.")
        if (
            not isinstance(settings["topics"], list)
            or not settings["topics"]
            or any(not isinstance(topic, str) or not topic for topic in settings["topics"])
            or any(topic not in {item.value for item in TOPIC_CATEGORIES[category]}
                   for topic in settings["topics"])
            or len(set(settings["topics"])) != len(settings["topics"])
        ):
            raise ValueError("Wybierz co najmniej jeden temat pojedynku.")
        if (
            isinstance(settings["difficulty"], bool)
            or not isinstance(settings["difficulty"], int)
            or not 1 <= settings["difficulty"] <= 5
        ):
            raise ValueError("Poziom trudności musi należeć do zakresu 1–5.")
