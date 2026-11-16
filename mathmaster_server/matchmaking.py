from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from mathmaster_server.schemas import MatchSettings


@dataclass(slots=True)
class QueueTicket:
    queue_id: str
    player_id: str
    nickname: str
    settings: MatchSettings
    rating: int
    created_at: float


class MatchmakingQueue:
    def __init__(self) -> None:
        self.tickets: dict[str, QueueTicket] = {}

    def add(
        self, player_id: str, nickname: str, settings: MatchSettings, rating: int
    ) -> QueueTicket:
        ticket = QueueTicket(
            queue_id=str(uuid.uuid4()),
            player_id=player_id,
            nickname=nickname,
            settings=settings,
            rating=rating,
            created_at=time.monotonic(),
        )
        self.tickets[player_id] = ticket
        return ticket

    def remove(self, player_id: str) -> QueueTicket | None:
        return self.tickets.pop(player_id, None)

    def group_for(
        self, ticket: QueueTicket, available_player_ids: set[str] | None = None
    ) -> list[QueueTicket]:
        desired = ticket.settings.player_count
        candidates_by_time = [
            item for item in self.tickets.values()
            if _compatible(ticket, item)
        ]
        waited = time.monotonic() - min(
            (item.created_at for item in candidates_by_time),
            default=ticket.created_at,
        )
        rating_window = min(4_000, 500 + int(waited // 10) * 250)
        candidates = [
            item for item in candidates_by_time
            if abs(ticket.rating - item.rating) <= rating_window
            and (
                available_player_ids is None
                or item.player_id in available_player_ids
            )
        ]
        candidates.sort(key=lambda item: (abs(ticket.rating - item.rating), item.created_at))
        return candidates[:desired] if len(candidates) >= desired else []


def _compatible(left: QueueTicket, right: QueueTicket) -> bool:
    return left.settings.model_dump() == right.settings.model_dump()

