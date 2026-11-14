import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.handlers import admin, common, fallback, sale
from app.bot.middlewares import ContextMiddleware
from app.config import Settings
from app.i18n import LANGS, default_lang, normalize, t

log = logging.getLogger(__name__)


def create_storage(settings: Settings) -> BaseStorage:
    if settings.REDIS_URL:
        from aiogram.fsm.storage.redis import RedisStorage

        # Drafts survive bot restarts; abandoned drafts expire after FSM_TTL_SECONDS.
        return RedisStorage.from_url(
            settings.REDIS_URL, state_ttl=settings.FSM_TTL_SECONDS, data_ttl=settings.FSM_TTL_SECONDS
        )
    log.warning("REDIS_URL is empty: using in-memory FSM storage (drafts are lost on restart)")
    return MemoryStorage()


def create_bot(settings: Settings) -> Bot:
    return Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=None))


def create_dispatcher(settings: Settings, session_maker: async_sessionmaker) -> Dispatcher:
    dp = Dispatcher(storage=create_storage(settings))
    dp.update.outer_middleware(ContextMiddleware(session_maker, settings))
    # order matters: common -> admin -> sale -> fallback
    dp.include_routers(common.router, admin.router, sale.router, fallback.router)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        log.exception("bot handler error", exc_info=event.exception)
        upd = event.update
        try:
            # The middleware's data is not available here: use the Telegram app language.
            if upd.message:
                lang = normalize(upd.message.from_user and upd.message.from_user.language_code) or default_lang()
                await upd.message.answer(t(lang, "error.generic"))
            elif upd.callback_query:
                lang = normalize(upd.callback_query.from_user.language_code) or default_lang()
                await upd.callback_query.answer(t(lang, "error.generic_short"), show_alert=True)
        except Exception:
            pass
        return True

    return dp


COMMANDS = ("start", "help", "myid", "cancel", "lang")


def bot_commands(lang: str) -> list[BotCommand]:
    return [BotCommand(command=c, description=t(lang, f"cmd.{c}")) for c in COMMANDS]


async def set_commands(bot: Bot) -> None:
    """Command menu per Telegram app language, plus the default one for every other language."""
    await bot.set_my_commands(bot_commands(default_lang()))
    for lang in LANGS:
        await bot.set_my_commands(bot_commands(lang), language_code=lang)
