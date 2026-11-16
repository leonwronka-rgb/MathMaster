from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from mathmaster_server.authentication import CurrentPlayer, DatabaseSession
from mathmaster_server.models import Battle, BattleParticipant, Player
from mathmaster_server.schemas import BattleHistoryEntry, LocalProfileLink, PlayerPublic

router = APIRouter(prefix="/v1/players", tags=["players"])


def player_public(player: Player) -> PlayerPublic:
    return PlayerPublic(
        id=player.id,
        nickname=player.nickname,
        rating=player.rating,
        matches=player.matches,
        wins=player.wins,
        losses=player.losses,
        draws=player.draws,
        correct_answers=player.correct_answers,
        mistakes=player.mistakes,
        win_rate=round(100 * player.wins / player.matches, 1) if player.matches else 0.0,
        created_at=player.created_at,
    )


@router.get("/me", response_model=PlayerPublic)
def get_me(player: CurrentPlayer):
    return player_public(player)


@router.put("/me/local-profile", response_model=PlayerPublic)
def link_local_profile(body: LocalProfileLink, player: CurrentPlayer, session: DatabaseSession):
    existing = session.scalar(
        select(Player).where(Player.local_profile_ref == body.local_profile_ref)
    )
    if existing is not None and existing.id != player.id:
        raise HTTPException(status_code=409, detail="This local profile reference is already linked.")
    player.local_profile_ref = body.local_profile_ref
    session.commit()
    session.refresh(player)
    return player_public(player)


@router.delete("/me/local-profile", response_model=PlayerPublic)
def unlink_local_profile(player: CurrentPlayer, session: DatabaseSession):
    player.local_profile_ref = None
    session.commit()
    session.refresh(player)
    return player_public(player)


@router.get("/me/history", response_model=list[BattleHistoryEntry])
def get_history(
    player: CurrentPlayer,
    session: DatabaseSession,
    limit: int = Query(default=50, ge=1, le=200),
):
    rows = session.execute(
        select(BattleParticipant, Battle)
        .join(Battle, Battle.id == BattleParticipant.battle_id)
        .where(BattleParticipant.player_id == player.id)
        .order_by(Battle.completed_at.desc())
        .limit(limit)
    ).all()
    return [
        BattleHistoryEntry(
            battle_id=battle.id,
            mode=battle.mode,
            difficulty=battle.difficulty,
            category=battle.category,
            duration_seconds=battle.duration_seconds,
            room_code=battle.room_code,
            completed_at=battle.completed_at,
            points=participant.points,
            correct_answers=participant.correct_answers,
            mistakes=participant.mistakes,
            place=participant.place,
            player_count=len(battle.participants),
            outcome=participant.outcome,
            rating_change=participant.rating_change,
        )
        for participant, battle in rows
    ]

