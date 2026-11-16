from __future__ import annotations

import base64
import binascii
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MATHMASTER_",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://mathmaster:mathmaster@localhost:5432/mathmaster"
    secret_key: str = ""
    access_token_minutes: int = Field(default=60 * 24 * 14, ge=5, le=60 * 24 * 90)
    result_signing_private_key: str = ""
    cors_origins: str = ""
    registration_enabled: bool = True
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    auth_rate_limit: int = Field(default=10, ge=1, le=1000)
    websocket_rate_limit: int = Field(default=30, ge=1, le=1000)
    battle_question_timeout_seconds: int = Field(default=20, ge=5, le=120)
    reconnect_grace_seconds: int = Field(default=60, ge=5, le=600)

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        if value and len(value.encode("utf-8")) < 32:
            raise ValueError("MATHMASTER_SECRET_KEY must contain at least 32 bytes.")
        return value

    def require_secrets(self) -> None:
        if len(self.secret_key.encode("utf-8")) < 32:
            raise RuntimeError("Set MATHMASTER_SECRET_KEY to a random value of at least 32 bytes.")
        if not self.result_signing_private_key:
            raise RuntimeError("Set MATHMASTER_RESULT_SIGNING_PRIVATE_KEY (base64 Ed25519 seed).")
        try:
            seed = base64.b64decode(self.result_signing_private_key, validate=True)
        except (binascii.Error, ValueError) as error:
            raise RuntimeError("Invalid base64 MATHMASTER_RESULT_SIGNING_PRIVATE_KEY.") from error
        if len(seed) != 32:
            raise RuntimeError("Ed25519 signing key must decode to exactly 32 bytes.")


@lru_cache
def get_settings() -> Settings:
    return Settings()

