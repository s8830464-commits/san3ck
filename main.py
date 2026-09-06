import asyncio
import logging
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.database.session import init_db, async_session_factory
from bot.web.exporter import sync_site_async
from bot.web.server import start_web_server, stop_web_server
from bot.middlewares.admin import AdminOnlyMiddleware
from bot.handlers import main_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("notes_bot")


async def main():
    logger.info("Starting Notes Garden Ecosystem...")

    # 1. Initialize database schema if not present
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully.")

    # 2. Synchronize site HTML & JSON with current database
    async with async_session_factory() as session:
        await sync_site_async(session)
        logger.info("Synchronized static website files.")

    # 4. Start local Web Server (serving website, REST API & SSE)
    logger.info(f"Starting web server on http://{settings.WEB_SERVER_HOST}:{settings.WEB_SERVER_PORT}...")
    await start_web_server()
    logger.info(f"🌿 Notes Garden Web Server is live at: {settings.WEB_SITE_URL}")

    # 5. Setup Bot & Dispatcher with HTML parse mode
    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # 6. Security: Attach Admin-only middleware to messages and callbacks
    admin_middleware = AdminOnlyMiddleware()
    dp.message.outer_middleware(admin_middleware)
    dp.callback_query.outer_middleware(admin_middleware)

    # 7. Attach handlers
    dp.include_router(main_router)

    # 8. Start Polling
    logger.info(f"Bot listening for updates (Admin ID: {settings.ADMIN_TELEGRAM_ID})...")
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down bot and web server...")
        await stop_web_server()
        await bot.session.close()



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
