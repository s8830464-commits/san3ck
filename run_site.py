"""
Standalone runner for Notes Garden Web Server.
Allows launching and previewing the website and REST API independently.
Usage:
    python run_site.py
"""

import sys
import os
import asyncio
import logging

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from bot.config import settings
from bot.database.session import init_db, async_session_factory
from bot.database.seed_data import seed_database
from bot.web.exporter import sync_site_async
from bot.web.server import start_web_server, stop_web_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("notes_garden")


async def main():
    logger.info("Initializing Notes Garden database...")
    await init_db()

    async with async_session_factory() as session:
        seeded = await seed_database(session, force=False)
        if seeded > 0:
            logger.info(f"Seeded {seeded} initial notes.")
        await sync_site_async(session)

    await start_web_server()
    print("\n" + "=" * 60)
    print(f"🌿 Notes Garden Web Server is RUNNING!")
    print(f"👉 Open in browser: {settings.WEB_SITE_URL}")
    print(f"📁 Local file view: file:///{os.path.abspath('site/index.html').replace(os.sep, '/')}")
    print("=" * 60 + "\n")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Stopping web server...")
        await stop_web_server()
        logger.info("Stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
