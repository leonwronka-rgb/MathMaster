from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

_NICKNAME = re.compile(r"^[A-Za-z0-9_]{3,24}$")


class RegisterRequest(BaseModel):
    email: EmailStr
    nickname: str = Field(min_length=3, max_length=24)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("nickname")
    @classmethod
    def valid_nickname(cls, value: str) -> str:
        value = value.strip()
        if not _NICKNAME.fullmatch(value):
            raise ValueError("Nickname must contain 3-24 letters, numbers, or underscores.")
        return value

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError("Password must contain at least one letter and one number.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class PlayerPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nickname: str
    rating: int
    matches: int
    wins: int
    losses: int
    draws: int
    correct_answers: int
    mistakes: int
    win_rate: float
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    player: PlayerPublic


class LocalProfileLink(BaseModel):
    local_profile_ref: str = Field(min_length=32, max_length=64, pattern=r"^[a-f0-9-]+$")


class BattleHistoryEntry(BaseModel):
    battle_id: str
    mode: str
    difficulty: str
    category: str
    duration_seconds: int
    room_code: str
    completed_at: datetime
    points: int
    correct_answers: int
    mistakes: int
    place: int
    player_count: int
    outcome: str
    rating_change: int


class LeaderboardEntry(BaseModel):
    rank: int
    player_id: str
    nickname: str
    rating: int
    matches: int
    wins: int
    losses: int
    win_rate: float


class MatchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["race", "survival"]
    duration_seconds: int
    player_count: int = Field(ge=2, le=8)
    category: str = Field(min_length=1, max_length=100)
    topics: list[str] = Field(min_length=1, max_length=30)
    difficulty: int = Field(ge=1, le=5)

    @model_validator(mode="after")
    def validate_mode_duration(self):
        if self.mode == "race" and self.duration_seconds not in {60, 120, 180}:
            raise ValueError("Race duration must be 60, 120, or 180 seconds.")
        if self.mode == "survival" and self.duration_seconds != 0:
            raise ValueError("Survival mode has no time limit.")
        if len(set(self.topics)) != len(self.topics):
            raise ValueError("Topic identifiers must be unique.")
        return self

