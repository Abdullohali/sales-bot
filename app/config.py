from decimal import Decimal
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    BOT_TOKEN: str = ""
    ADMIN_IDS: Annotated[list[int], NoDecode] = []
    # Webhook: if WEBHOOK_BASE_URL is empty, the bot runs in polling mode (local dev).
    WEBHOOK_BASE_URL: str = ""
    WEBHOOK_PATH: str = "/webhook"
    WEBHOOK_SECRET: str = ""

    # Business
    VAT_RATE: Decimal = Decimal("12")
    COMPANY_NAME: str = "ООО «Компания»"
    COMPANY_INN: str = ""
    TIMEZONE: str = "Asia/Tashkent"
    # uz | ru | en: used when the user's language is unknown (bot) or not chosen (panel)
    DEFAULT_LANGUAGE: str = "ru"

    # Infrastructure
    DATABASE_URL: str = "postgresql+asyncpg://salesbot:salesbot@localhost:5432/salesbot"
    REDIS_URL: str = ""  # empty -> in-memory FSM storage (dev only)
    FSM_TTL_SECONDS: int = 60 * 60 * 24  # unfinished drafts expire after 24h

    # Admin panel
    ADMIN_SECRET_KEY: str = "change-me"

    # Monitoring
    SENTRY_DSN: str = ""
    ENVIRONMENT: str = "production"

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def _split_ids(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.replace(" ", "").split(",") if x]
        if isinstance(v, int):
            return [v]
        return v

    @property
    def webhook_url(self) -> str:
        return self.WEBHOOK_BASE_URL.rstrip("/") + self.WEBHOOK_PATH


@lru_cache
def get_settings() -> Settings:
    return Settings()
