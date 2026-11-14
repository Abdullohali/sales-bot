from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.filters import Filter
from aiogram.types import TelegramObject, User
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.i18n import normalize, resolve
from app.services.catalog import get_lang, get_role


class ContextMiddleware(BaseMiddleware):
    """Opens a DB session per update and resolves:
    - role: admin / courier / None (stranger)
    - lang: saved choice (/lang) -> Telegram app language -> DEFAULT_LANGUAGE
    - lang_saved: whether the language is stored in bot_users"""

    def __init__(self, session_maker: async_sessionmaker, settings: Settings) -> None:
        self.session_maker = session_maker
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        async with self.session_maker() as session:
            data["session"] = session
            data["settings"] = self.settings
            data["role"] = await get_role(session, user.id, self.settings.ADMIN_IDS) if user else None
            saved = await get_lang(session, user.id) if user else None
            data["lang_saved"] = saved is not None
            data["lang"] = saved or resolve(normalize(user.language_code) if user else None)
            return await handler(event, data)


class RoleFilter(Filter):
    def __init__(self, *roles: str) -> None:
        self.roles = roles

    async def __call__(self, event: TelegramObject, role: str | None = None) -> bool:
        return role in self.roles
