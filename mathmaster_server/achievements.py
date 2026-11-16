from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from mathmaster_server.authentication import CurrentPlayer, DatabaseSession
from mathmaster_server.database import Base

router = APIRouter(prefix="/v1/players/me/achievements", tags=["achievements"])

ACHIEVEMENTS = {
    "first_match": ("Pierwszy pojedynek", "Ukończ pierwszy Quiz Battle."),
    "first_win": ("Pierwsze zwycięstwo", "Wygraj pierwszy pojedynek."),
    "five_wins": ("Zwycięzca", "Wygraj pięć pojedynków."),
    "ten_wins": ("Mistrz pojedynków", "Wygraj dziesięć pojedynków."),
    "ten_matches": ("Regularny gracz", "Ukończ dziesięć pojedynków."),
    "hundred_correct": ("Matematyczna precyzja", "Udziel stu poprawnych odpowiedzi."),
}


class PlayerAchievement(Base):
    __tablename__ = "player_achievements"
    __table_args__ = (
        UniqueConstraint("player_id", "achievement_key", name="uq_player_achievement"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    achievement_key: Mapped[str] = mapped_column(String(40))
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def unlock_eligible_achievements(session: Session, player) -> list[str]:
    eligible = []
    if player.matches >= 1:
        eligible.append("first_match")
    if player.wins >= 1:
        eligible.append("first_win")
    if player.wins >= 5:
        eligible.append("five_wins")
    if player.wins >= 10:
        eligible.append("ten_wins")
    if player.matches >= 10:
        eligible.append("ten_matches")
    if player.correct_answers >= 100:
        eligible.append("hundred_correct")
    existing = set(session.scalars(
        select(PlayerAchievement.achievement_key).where(
            PlayerAchievement.player_id == player.id,
            PlayerAchievement.achievement_key.in_(eligible or [""]),
        )
    ).all())
    newly_unlocked = [key for key in eligible if key not in existing]
    session.add_all(
        PlayerAchievement(player_id=player.id, achievement_key=key)
        for key in newly_unlocked
    )
    return newly_unlocked


@router.get("")
def get_achievements(player: CurrentPlayer, session: DatabaseSession):
    unlocked = set(session.scalars(
        select(PlayerAchievement.achievement_key).where(
            PlayerAchievement.player_id == player.id
        )
    ).all())
    return [
        {
            "key": key,
            "title": title,
            "description": description,
            "unlocked": key in unlocked,
        }
        for key, (title, description) in ACHIEVEMENTS.items()
    ]

