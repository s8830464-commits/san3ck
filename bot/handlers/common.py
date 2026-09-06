from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from bot.config import settings
from bot.database.session import async_session_factory
from bot.database import crud

router = Router(name="common_router")


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handler for /start command."""
    welcome_text = (
        "<b>FastNotes</b>\n\n"
        "Отправьте любую мысль или задачу — сохраню и структурирую.\n\n"
        f"🌐 Сайт: {settings.WEB_SITE_URL}"
    )
    await message.answer(welcome_text, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handler for /help command."""
    await cmd_start(message)


@router.message(Command("site"))
@router.message(Command("web"))
async def cmd_site(message: Message):
    """Handler for /site and /web command."""
    async with async_session_factory() as session:
        count = await crud.count_notes(session, status="published")

    text = (
        "<b>FastNotes</b>\n\n"
        f"Опубликовано заметок: <b>{count}</b>\n"
        f"🌐 Сайт: {settings.WEB_SITE_URL}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("allow"))
@router.message(Command("add_user"))
async def cmd_allow_user(message: Message):
    """Allow a user ID to use the bot (admin only)."""
    from bot.middlewares.admin import add_allowed_user
    if message.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await message.answer("⛔ Управлять доступом может только главный администратор.")
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Укажите ID: <code>/allow &lt;id&gt;</code>\nНапример: <code>/allow 816827728</code>", parse_mode="HTML")
        return

    target_id = int(args[1])
    add_allowed_user(target_id)
    await message.answer(f"✅ Доступ для ID <code>{target_id}</code> успешно открыт!", parse_mode="HTML")


@router.message(Command("disallow"))
async def cmd_disallow_user(message: Message):
    """Revoke access for a user ID (admin only)."""
    from bot.middlewares.admin import remove_allowed_user
    if message.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await message.answer("⛔ Управлять доступом может только главный администратор.")
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Укажите ID: <code>/disallow &lt;id&gt;</code>", parse_mode="HTML")
        return

    target_id = int(args[1])
    if target_id == settings.ADMIN_TELEGRAM_ID:
        await message.answer("⚠️ Нельзя отозвать доступ у главного администратора.")
        return

    remove_allowed_user(target_id)
    await message.answer(f"🚫 Доступ для ID <code>{target_id}</code> закрыт.", parse_mode="HTML")


@router.message(Command("users"))
async def cmd_list_users(message: Message):
    """List all allowed user IDs (admin only)."""
    from bot.middlewares.admin import get_allowed_users
    if message.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await message.answer("⛔ Список пользователей доступен только главному администратору.")
        return

    users = get_allowed_users()
    user_lines = [f"• <code>{uid}</code>" + (" 👑 (Главный админ)" if uid == settings.ADMIN_TELEGRAM_ID else "") for uid in sorted(users)]
    await message.answer("👥 <b>Разрешённые пользователи:</b>\n\n" + "\n".join(user_lines), parse_mode="HTML")


@router.message(lambda msg: bool(msg.document and msg.document.file_name and msg.document.file_name.lower().endswith((".html", ".htm"))))
async def handle_html_document(message: Message):
    """Allow updating website by sending an HTML file into Telegram."""
    if message.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await message.answer("⛔ Обновлять шаблон сайта может только главный администратор.")
        return

    doc = message.document
    await message.bot.send_chat_action(chat_id=message.chat.id, action="upload_document")
    file = await message.bot.get_file(doc.file_id)
    dest_path = "site/index.html"
    await message.bot.download_file(file.file_path, dest_path)

    # Sync existing database notes into the uploaded HTML
    async with async_session_factory() as session:
        from bot.web.exporter import sync_site_async
        await sync_site_async(session)

    try:
        from bot.web.server import broadcast_sse
        await broadcast_sse("notes_refreshed", {})
    except Exception:
        pass

    await message.answer(
        "✅ <b>Сайт успешно обновлён!</b>\n"
        f"Файл <code>{doc.file_name}</code> установлен в качестве главной страницы сайта. "
        "Все текущие заметки автоматически синхронизированы.",
        parse_mode="HTML"
    )
