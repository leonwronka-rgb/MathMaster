from __future__ import annotations

import base64
import json
import unittest
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi.testclient import TestClient

from mathmaster_server.battles import SUPPORTED_CATEGORY_TOPICS
from mathmaster_server.config import Settings
from mathmaster_server.main import create_app
from mathmaster_server.questions import SUPPORTED_TOPICS, answers_equal, generate_question
from mathmaster_server.schemas import MatchSettings
from mathmaster_server.websocket import _validate_message


def test_settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        secret_key="test-secret-" + "x" * 40,
        result_signing_private_key=base64.b64encode(b"0123456789abcdef0123456789abcdef").decode(),
        battle_question_timeout_seconds=8,
        reconnect_grace_seconds=5,
    )


class BackendApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(test_settings())
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def register(self, nickname: str) -> dict[str, object]:
        response = self.client.post(
            "/v1/auth/register",
            json={
                "email": f"{nickname.lower()}@example.com",
                "nickname": nickname,
                "password": "secure-password-2026",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_registration_login_and_optional_local_link(self) -> None:
        account = self.register("Algebra_1")
        token = account["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        me = self.client.get("/v1/players/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["nickname"], "Algebra_1")

        conflict = self.client.post(
            "/v1/auth/register",
            json={
                "email": "ALgebra_1@example.com",
                "nickname": "algebra_1",
                "password": "another-secure-2026",
            },
        )
        self.assertEqual(conflict.status_code, 409)

        local_ref = str(uuid.uuid4())
        linked = self.client.put(
            "/v1/players/me/local-profile",
            headers=headers,
            json={"local_profile_ref": local_ref},
        )
        self.assertEqual(linked.status_code, 200)
        unlinked = self.client.delete("/v1/players/me/local-profile", headers=headers)
        self.assertEqual(unlinked.status_code, 200)

        login = self.client.post(
            "/v1/auth/login",
            json={"email": "ALGEBRA_1@example.com", "password": "secure-password-2026"},
        )
        self.assertEqual(login.status_code, 200)
        rejected = self.client.post(
            "/v1/auth/login",
            json={"email": "algebra_1@example.com", "password": "incorrect-password"},
        )
        self.assertEqual(rejected.status_code, 401)

    def test_multiplayer_scores_are_server_checked_and_individually_signed(self) -> None:
        first = self.register("Player_A")
        second = self.register("Player_B")
        first_token, second_token = first["access_token"], second["access_token"]
        settings = {
            "mode": "survival",
            "duration_seconds": 0,
            "player_count": 2,
            "category": "Arytmetyka",
            "topics": ["addition"],
            "difficulty": 2,
        }

        with (
            self.client.websocket_connect("/v1/ws") as socket_a,
            self.client.websocket_connect("/v1/ws") as socket_b,
        ):
            socket_a.send_json({
                "type": "authenticate",
                "token": first_token,
                "display_name": "spoofed name",
                "protocol_version": 1,
            })
            self.assertEqual(socket_a.receive_json()["type"], "authenticated")
            socket_b.send_json({
                "type": "authenticate",
                "token": second_token,
                "display_name": "another spoofed name",
                "protocol_version": 1,
            })
            self.assertEqual(socket_b.receive_json()["type"], "authenticated")

            socket_a.send_json({"type": "matchmaking_join", "settings": settings, "friends_only": False})
            self.assertEqual(socket_a.receive_json()["type"], "waiting")
            socket_b.send_json({"type": "matchmaking_join", "settings": settings, "friends_only": False})
            self.assertEqual(socket_b.receive_json()["type"], "waiting")
            start_a = self._receive_until(socket_a, "match_started")
            start_b = self._receive_until(socket_b, "match_started")
            self.assertEqual(len(start_a["players"]), 2)
            self.assertEqual(start_a["match_id"], start_b["match_id"])
            question = start_a["question"]
            self.assertNotIn("answer", question)
            match = self.app.state.battle_manager.matches[start_a["match_id"]]
            expected = match.current_question.answer
            question_id = question["question_id"]

            socket_a.send_json({
                "type": "answer_submit", "question_id": question_id, "answer": expected,
            })
            self._receive_until(socket_a, "players_updated")
            socket_b.receive_json()
            socket_a.send_json({
                "type": "answer_submit", "question_id": question_id, "answer": expected,
            })
            self.assertEqual(self._receive_until(socket_a, "error")["type"], "error")

            socket_b.send_json({
                "type": "answer_submit", "question_id": question_id, "answer": expected,
            })
            self._receive_until(socket_a, "answer_result")
            self._receive_until(socket_b, "answer_result")
            socket_b.send_json({"type": "match_leave"})
            result_a = self._receive_until(socket_a, "match_finished")
            result_b = self._receive_until(socket_b, "match_finished")
            socket_a.send_json({"type": "resume", "match_id": start_a["match_id"]})
            replayed_result = self._receive_until(socket_a, "match_finished")
            self.assertEqual(replayed_result["signed_payload"], result_a["signed_payload"])

        public_key_text = self.client.get("/v1/metadata").json()["result_public_key"]
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_text))
        payload_a = base64.b64decode(result_a["signed_payload"])
        payload_b = base64.b64decode(result_b["signed_payload"])
        public_key.verify(base64.b64decode(result_a["signature"]), payload_a)
        public_key.verify(base64.b64decode(result_b["signature"]), payload_b)
        data_a, data_b = json.loads(payload_a), json.loads(payload_b)
        self.assertEqual(data_a["player_id"], first["player"]["id"])
        self.assertEqual(data_b["player_id"], second["player"]["id"])
        self.assertEqual(data_a["winner_player_id"], data_b["winner_player_id"])
        self.assertEqual(len(data_a["standings"]), 2)

        history_a = self.client.get(
            "/v1/players/me/history",
            headers={"Authorization": f"Bearer {first_token}"},
        )
        history_b = self.client.get(
            "/v1/players/me/history",
            headers={"Authorization": f"Bearer {second_token}"},
        )
        self.assertEqual(len(history_a.json()), 1)
        self.assertEqual(len(history_b.json()), 1)
        self.assertEqual(self.client.get("/health").json()["status"], "ok")

    def test_private_room_waits_for_real_players_before_starting(self) -> None:
        host = self.register("Room_Host")
        guest = self.register("Room_Guest")
        settings = {
            "mode": "race",
            "duration_seconds": 60,
            "player_count": 3,
            "category": "Arytmetyka",
            "topics": ["addition"],
            "difficulty": 2,
        }
        with (
            self.client.websocket_connect("/v1/ws") as socket_host,
            self.client.websocket_connect("/v1/ws") as socket_guest,
        ):
            for socket, account in ((socket_host, host), (socket_guest, guest)):
                socket.send_json({
                    "type": "authenticate",
                    "token": account["access_token"],
                    "display_name": account["player"]["nickname"],
                    "protocol_version": 1,
                })
                self.assertEqual(socket.receive_json()["type"], "authenticated")

            socket_host.send_json({"type": "room_create", "settings": settings, "friends_only": True})
            room = socket_host.receive_json()
            self.assertEqual(room["type"], "room_created")
            self.assertEqual(len(room["players"]), 1)
            socket_host.send_json({"type": "room_start", "room_code": room["room_code"]})
            self.assertEqual(self._receive_until(socket_host, "error")["type"], "error")

            socket_guest.send_json({"type": "room_join", "room_code": room["room_code"]})
            joined = self._receive_until(socket_guest, "room_joined")
            self.assertEqual(len(joined["players"]), 2)
            self.assertIsNone(self.app.state.battle_manager.rooms[room["room_code"]].match_id)

            socket_host.send_json({"type": "room_start", "room_code": room["room_code"]})
            start_host = self._receive_until(socket_host, "match_started")
            start_guest = self._receive_until(socket_guest, "match_started")
            self.assertEqual(start_host["match_id"], start_guest["match_id"])
            self.assertEqual(len(start_host["players"]), 2)

    @staticmethod
    def _receive_until(socket, event_type: str) -> dict[str, object]:
        for _ in range(20):
            message = socket.receive_json()
            if message.get("type") == event_type:
                return message
        raise AssertionError(f"Did not receive WebSocket event {event_type!r}.")


class QuestionAndValidationTests(unittest.TestCase):
    def test_answer_comparison_handles_fraction_and_rejects_expressions(self) -> None:
        self.assertTrue(answers_equal(" 6/8 ", "3/4"))
        self.assertTrue(answers_equal("1,25", "5/4"))
        self.assertFalse(answers_equal("__import__('os')", "1"))

    def test_server_question_never_exposes_its_solution(self) -> None:
        settings = MatchSettings(
            mode="race",
            duration_seconds=60,
            player_count=2,
            category="Arytmetyka",
            topics=["addition"],
            difficulty=2,
        )
        question = generate_question(settings)
        public = question.public(number=1, count=0, remaining_seconds=10)
        self.assertNotIn("answer", public)
        self.assertTrue(question.answer)

    def test_every_enabled_topic_generates_a_checkable_question(self) -> None:
        self.assertEqual(
            set().union(*SUPPORTED_CATEGORY_TOPICS.values()),
            SUPPORTED_TOPICS,
        )
        for category, topics in SUPPORTED_CATEGORY_TOPICS.items():
            for topic in topics:
                with self.subTest(category=category, topic=topic):
                    settings = MatchSettings(
                        mode="race",
                        duration_seconds=60,
                        player_count=2,
                        category=category,
                        topics=[topic],
                        difficulty=3,
                    )
                    question = generate_question(settings)
                    self.assertEqual(question.topic, topic)
                    self.assertRegex(question.answer, r"^[+-]?\d+(?:/\d+)?$")

    def test_websocket_rejects_unexpected_and_oversized_fields(self) -> None:
        with self.assertRaises(ValueError):
            _validate_message({"type": "match_leave", "points": 1000})
        with self.assertRaises(ValueError):
            _validate_message({"type": "answer_submit", "question_id": "id", "answer": 2})


if __name__ == "__main__":
    unittest.main()
