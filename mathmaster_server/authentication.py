from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mathmaster_server.config import Settings
from mathmaster_server.database import get_session
from mathmaster_server.models import Player
from mathmaster_server.rate_limit import client_key
from mathmaster_server.schemas import LoginRequest, PlayerPublic, RegisterRequest, TokenResponse

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/v1/auth", tags=["authentication"])


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(player_id: str, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": player_id,
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
            "iss": "mathmaster-server",
        },
        settings.secret_key,
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> str:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            issuer="mathmaster-server",
            options={"require": ["sub", "exp", "iat", "iss"]},
        )
    except jwt.InvalidTokenError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.") from error
    player_id = payload.get("sub")
    if not isinstance(player_id, str) or not player_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject.")
    return player_id


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_current_player(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> Player:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer token required.")
    player_id = decode_access_token(credentials.credentials, settings)
    player = session.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=401, detail="Player account no longer exists.")
    return player


CurrentPlayer = Annotated[Player, Depends(get_current_player)]
DatabaseSession = Annotated[Session, Depends(get_session)]


def _player_public(player: Player) -> PlayerPublic:
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


def _token_response(player: Player, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(player.id, settings),
        expires_in=settings.access_token_minutes * 60,
        player=_player_public(player),
    )


def _limit_auth(request: Request) -> None:
    settings: Settings = request.app.state.settings
    request.app.state.rate_limiter.check(
        client_key(request, "auth"),
        limit=settings.auth_rate_limit,
        window_seconds=settings.rate_limit_window_seconds,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, request: Request, session: DatabaseSession):
    _limit_auth(request)
    if not request.app.state.settings.registration_enabled:
        raise HTTPException(status_code=403, detail="Online registration is disabled.")
    email = str(body.email).strip().lower()
    nickname = body.nickname.strip()
    existing = session.scalar(
        select(Player).where(
            (Player.email == email) | (Player.nickname_key == nickname.casefold())
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email or nickname is already registered.")
    player = Player(
        nickname=nickname,
        nickname_key=nickname.casefold(),
        email=email,
        password_hash=hash_password(body.password),
    )
    session.add(player)
    try:
        session.commit()
        session.refresh(player)
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="Email or nickname is already registered.") from error
    return _token_response(player, request.app.state.settings)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, session: DatabaseSession):
    _limit_auth(request)
    player = session.scalar(select(Player).where(Player.email == str(body.email).lower()))
    if player is None or not verify_password(player.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if password_hasher.check_needs_rehash(player.password_hash):
        player.password_hash = hash_password(body.password)
        session.commit()
    return _token_response(player, request.app.state.settings)

