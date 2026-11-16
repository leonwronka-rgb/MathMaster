from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from accounts.auth import AuthService
from database.database import Database
from gamification.service import GamificationService
from quiz_battle.client import QuizBattleClient, QuizBattleConnectionError
from quiz_battle.service import QuizBattleService
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class QuizBattleServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "battle.sqlite3")
        self.database.initialize()
        self.user = AuthService(self.database).register(
            "battle-player", "Battle Player", "secure-pass-123"
        )
        self.gamification = GamificationService(self.database)
        self.service = QuizBattleService(self.database, self.gamification)
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.database.close)

    def test_stats_and_history_are_empty_until_a_verified_result_is_saved(self) -> None:
        stats = self.service.get_stats(self.user.id)
        self.assertEqual(
            (stats.matches, stats.wins, stats.losses, stats.win_rate),
            (0, 0, 0, 0.0),
        )
        self.assertEqual(self.service.get_history(self.user.id), ())

    def test_settings_validate_real_match_constraints(self) -> None:
        valid = {
            "mode": "race",
            "duration_seconds": 120,
            "player_count": 8,
            "category": "Algebra",
            "topics": ["linear_equation"],
            "difficulty": 3,
        }
        QuizBattleService._validate_settings(valid)
        invalid = {**valid, "player_count": 9}
        with self.assertRaises(ValueError):
            QuizBattleService._validate_settings(invalid)
        invalid_topics = {**valid, "topics": []}
        with self.assertRaises(ValueError):
            QuizBattleService._validate_settings(invalid_topics)

    def test_client_requires_secure_remote_transport_and_no_bot_fallback(self) -> None:
        client = QuizBattleClient()
        with self.assertRaises(QuizBattleConnectionError):
            client.connect(
                "ws://public.example/quiz",
                "server-token",
                "Battle Player",
                lambda _event: None,
            )
        with self.assertRaises(QuizBattleConnectionError):
            client.send("matchmaking_join")
        self.assertFalse(client.running)

    def test_only_a_signed_result_for_authenticated_player_is_saved(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self.service.gamification = GamificationService(self.database, public_key)
        self.service._user_id = self.user.id
        self.service._player_id = "server-user-7"
        payload = {
            "battle_id": "match-42",
            "player_id": "server-user-7",
            "winner_player_id": "server-user-7",
            "mode": "race",
            "difficulty": "medium",
            "completed_at": "2026-11-12T14:00:00+00:00",
            "duration_seconds": 60,
            "room_code": "FRIEND42",
            "standings": [
                {
                    "player_id": "server-user-7",
                    "display_name": "Battle Player",
                    "points": 100,
                    "correct_answers": 4,
                    "mistakes": 0,
                    "eliminated": False,
                    "place": 1,
                },
                {
                    "player_id": "server-user-8",
                    "display_name": "Opponent",
                    "points": 80,
                    "correct_answers": 3,
                    "mistakes": 1,
                    "eliminated": False,
                    "place": 2,
                },
            ],
        }
        signed = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        event: dict[str, object] = {
            "type": "match_finished",
            "signed_payload": base64.b64encode(signed).decode(),
            "signature": base64.b64encode(private_key.sign(signed)).decode(),
        }

        self.service._handle_server_message(event)

        self.assertEqual(event["type"], "match_finished")
        result = event["verified_result"]
        self.assertEqual(result["outcome"], "win")
        self.assertEqual(result["points"], 100)
        self.assertEqual(result["xp_awarded"], 80)
        self.assertEqual(len(result["standings"]), 2)
        stats = self.service.get_stats(self.user.id)
        self.assertEqual((stats.matches, stats.wins, stats.correct_answers), (1, 1, 4))

        invalid: dict[str, object] = {
            "type": "match_finished",
            "signed_payload": base64.b64encode(
                signed.replace(b"server-user-7", b"server-user-9")
            ).decode(),
            "signature": event["signature"],
        }
        self.service._handle_server_message(invalid)
        self.assertEqual(invalid["type"], "result_rejected")
        self.assertEqual(self.service.get_stats(self.user.id).matches, 1)


if __name__ == "__main__":
    unittest.main()
