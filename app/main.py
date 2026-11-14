"""Single process: FastAPI serves the Telegram webhook, the admin panel and /health."""

import asyncio
import contextlib
import logging
import secrets
from contextlib import asynccontextmanager

from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from sqlalchemy import text

from app.admin import setup_admin
from app.bot.setup import create_bot, create_dispatcher, set_commands
from app.config import get_settings
from app.db.session import SessionLocal, engine

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

if settings.SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=settings.SENTRY_DSN, environment=settings.ENVIRONMENT, traces_sample_rate=0.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    polling_task: asyncio.Task | None = None
    bot = dp = None
    if settings.BOT_TOKEN:
        bot = create_bot(settings)
        dp = create_dispatcher(settings, SessionLocal)
        await set_commands(bot)
        if settings.WEBHOOK_BASE_URL:
            await bot.set_webhook(
                settings.webhook_url,
                secret_token=settings.WEBHOOK_SECRET or None,
                allowed_updates=dp.resolve_used_update_types(),
            )
            log.info("webhook set: %s", settings.webhook_url)
        else:
            await bot.delete_webhook(drop_pending_updates=False)
            polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
            log.info("WEBHOOK_BASE_URL is empty: running in polling mode")
    else:
        log.warning("BOT_TOKEN is empty: bot disabled, only admin panel is running")
    app.state.bot, app.state.dp = bot, dp

    yield

    if polling_task:
        polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await polling_task
    if dp:
        await dp.storage.close()
    if bot:
        await bot.session.close()
    await engine.dispose()


app = FastAPI(title="Sales bot", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
setup_admin(app, engine, settings.ADMIN_SECRET_KEY)


@app.post(settings.WEBHOOK_PATH, include_in_schema=False)
async def telegram_webhook(
    request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)
) -> dict:
    bot, dp = request.app.state.bot, request.app.state.dp
    if bot is None:
        raise HTTPException(status_code=503, detail="bot disabled")
    if settings.WEBHOOK_SECRET and not secrets.compare_digest(
        x_telegram_bot_api_secret_token or "", settings.WEBHOOK_SECRET
    ):
        raise HTTPException(status_code=403)
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.get("/health")
async def health() -> dict:
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root():
    from starlette.responses import RedirectResponse

    return RedirectResponse("/admin")
