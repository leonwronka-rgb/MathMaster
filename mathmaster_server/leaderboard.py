from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import case, desc, select

from mathmaster_server.authentication import CurrentPlayer, DatabaseSession
from mathmaster_server.models import Player
from mathmaster_server.schemas import LeaderboardEntry

router = APIRouter(prefix="/v1/leaderboard", tags=["leaderboard"])


@router.get("", response_model=list[LeaderboardEntry])
def get_leaderboard(
    _player: CurrentPlayer,
    session: DatabaseSession,
    sort_by: Literal["rating", "wins", "win_rate"] = Query(default="rating"),
    limit: int = Query(default=100, ge=1, le=100),
):
    win_rate = case((Player.matches > 0, Player.wins * 1.0 / Player.matches), else_=0.0)
    sort_column = {
        "rating": Player.rating,
        "wins": Player.wins,
        "win_rate": win_rate,
    }[sort_by]
    players = session.scalars(
        select(Player)
        .where(Player.matches > 0)
        .order_by(desc(sort_column), desc(Player.rating), Player.id)
        .limit(limit)
    ).all()
    return [
        LeaderboardEntry(
            rank=index,
            player_id=player.id,
            nickname=player.nickname,
            rating=player.rating,
            matches=player.matches,
            wins=player.wins,
            losses=player.losses,
            win_rate=round(100 * player.wins / player.matches, 1) if player.matches else 0.0,
        )
        for index, player in enumerate(players, start=1)
    ]

