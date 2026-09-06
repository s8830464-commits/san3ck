import json
import logging
import os
from typing import Any, Awaitable, Callable, Dict, Set
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from bot.config import settings

logger = logging.getLogger("admin_middleware")

ALLOWED_USERS_FILE = "allowed_users.json"


def get_allowed_users() -> Set[int]:
    """Return set of all allowed Telegram user IDs."""
    allowed = {settings.ADMIN_TELEGRAM_ID}
    # Parse from settings / env
    raw = getattr(settings, "ALLOWED_TELEGRAM_IDS", "")
    for p in str(raw).split(","):
        p = p.strip()
        if p.isdigit():
            allowed.add(int(p))

    # Read from local JSON file
    if os.path.exists(ALLOWED_USERS_FILE):
        try:
            with open(ALLOWED_USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for uid in data:
                        if isinstance(uid, int):
                            allowed.add(uid)
        except Exception:
            pass

    return allowed


def add_allowed_user(user_id: int):
    """Add a user ID to allowed users list."""
    users = get_allowed_users()
    users.add(user_id)
    try:
        with open(ALLOWED_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(users)), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save allowed_users.json: {e}")


def remove_allowed_user(user_id: int):
    """Remove a user ID from allowed users list (admin cannot be removed)."""
    users = get_allowed_users()
    users.discard(user_id)
    users.add(settings.ADMIN_TELEGRAM_ID)
    try:
        with open(ALLOWED_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(users)), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save allowed_users.json: {e}")


class AdminOnlyMiddleware(BaseMiddleware):
    """Middleware enforcing that only allowed user IDs can interact with the bot."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = getattr(event, "from_user", None) or data.get("event_from_user")
        user_id = user.id if user else None

        if isinstance(event, Message):
            logger.info(f"Message from user_id={user_id} (@{user.username if user else 'none'}): {event.text}")
        elif isinstance(event, CallbackQuery):
            logger.info(f"Callback from user_id={user_id}: {event.data}")

        allowed = get_allowed_users()
        if not user or user_id not in allowed:
            logger.warning(f"Unauthorized access attempt by user_id={user_id} (Allowed: {allowed})")
            if isinstance(event, Message):
                await event.answer(f"⛔ Доступ закрыт.\nВаш Telegram ID: <code>{user_id}</code>.\nПопросите администратора добавить ваш ID в список разрешённых.", parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer(f"⛔ Доступ закрыт (ID: {user_id}).", show_alert=True)
            return

        return await handler(event, data)
