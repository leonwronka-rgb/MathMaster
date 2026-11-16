from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mathmaster_server.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nickname: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    nickname_key: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    rating: Mapped[int] = mapped_column(Integer, default=1000)
    matches: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    mistakes: Mapped[int] = mapped_column(Integer, default=0)
    local_profile_ref: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )

    participants: Mapped[list[BattleParticipant]] = relationship(back_populates="player")


class Battle(Base):
    __tablename__ = "battles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16))
    difficulty: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(100))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    room_code: Mapped[str] = mapped_column(String(24), default="")
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    winner_player_id: Mapped[str | None] = mapped_column(ForeignKey("players.id"), nullable=True)

    participants: Mapped[list[BattleParticipant]] = relationship(back_populates="battle", cascade="all, delete-orphan")


class BattleParticipant(Base):
    __tablename__ = "battle_participants"
    __table_args__ = (
        UniqueConstraint("battle_id", "player_id", name="uq_battle_player"),
        Index("ix_battle_participant_player_battle", "player_id", "battle_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    battle_id: Mapped[str] = mapped_column(ForeignKey("battles.id", ondelete="CASCADE"))
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    points: Mapped[int] = mapped_column(Integer, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    mistakes: Mapped[int] = mapped_column(Integer, default=0)
    eliminated: Mapped[bool] = mapped_column(Boolean, default=False)
    place: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(12))
    rating_change: Mapped[int] = mapped_column(Integer, default=0)

    battle: Mapped[Battle] = relationship(back_populates="participants")
    player: Mapped[Player] = relationship(back_populates="participants")

