import html
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import settings
from bot.database.session import async_session_factory
from bot.database import crud
from bot.keyboards.inline import (
    get_note_action_keyboard,
    get_pagination_keyboard,
)
from bot.utils import extract_tags, format_note_card, format_notes_list

router = Router(name="notes_router")


@router.message(Command("notes"))
@router.message(Command("list"))
async def cmd_list_notes(message: Message):
    """Show list of notes with pagination."""
    per_page = settings.DEFAULT_NOTES_PER_PAGE
    async with async_session_factory() as session:
        total_count = await crud.count_notes(session)
        notes = await crud.get_notes(session, limit=per_page, offset=0)

    total_pages = (total_count + per_page - 1) // per_page
    text = format_notes_list(notes, page=0, total_count=total_count, per_page=per_page)
    keyboard = get_pagination_keyboard(current_page=0, total_pages=total_pages, notes=notes)

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("page:"))
async def cb_pagination(callback: CallbackQuery):
    """Handle pagination page change."""
    page = int(callback.data.split(":")[1])
    per_page = settings.DEFAULT_NOTES_PER_PAGE

    async with async_session_factory() as session:
        total_count = await crud.count_notes(session)
        total_pages = (total_count + per_page - 1) // per_page
        page = max(0, min(page, max(0, total_pages - 1)))
        notes = await crud.get_notes(session, limit=per_page, offset=page * per_page)

    text = format_notes_list(notes, page=page, total_count=total_count, per_page=per_page)
    keyboard = get_pagination_keyboard(current_page=page, total_pages=total_pages, notes=notes)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("view:"))
async def cb_view_note(callback: CallbackQuery):
    """View full note card with action buttons."""
    note_id = int(callback.data.split(":")[1])
    async with async_session_factory() as session:
        note = await crud.get_note_by_id(session, note_id)

    if not note:
        await callback.answer("❌ Заметка не найдена.", show_alert=True)
        return

    text = format_note_card(note)
    keyboard = get_note_action_keyboard(note)
    await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    """Dummy callback for indicators."""
    await callback.answer()


@router.message(Command("ask"))
@router.message(Command("q"))
async def cmd_ask_notes(message: Message):
    """Explicit command to ask a question about existing notes."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer("💬 Задайте вопрос по заметкам. Например:\n<code>/ask какая цель проекта?</code>", parse_mode="HTML")
        return

    query = args[1].strip()
    await process_user_text_message(message, query, force_question=True)


@router.message(F.text, ~F.text.startswith("/"))
async def handle_new_note_text(message: Message):
    """
    Handle plain text message.
    Intelligently determines whether the user is asking a question about existing notes
    or creating a new note.
    """
    text = message.text.strip()
    if not text:
        return

    await process_user_text_message(message, text, force_question=False)


async def process_user_text_message(message: Message, text: str, force_question: bool = False):
    """Shared processing for questions and new notes."""
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Detect if replying to a specific note card in Telegram
    replied_note_id = None
    if message.reply_to_message and message.reply_to_message.reply_markup:
        for row in message.reply_to_message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and (btn.callback_data.startswith("edit:") or btn.callback_data.startswith("delete:")):
                    try:
                        replied_note_id = int(btn.callback_data.split(":")[1])
                        break
                    except (ValueError, IndexError):
                        pass

    from bot.services.ai_enhancer import process_user_message_async, SECTION_LABELS

    async with async_session_factory() as session:
        existing_notes = await crud.get_notes(session, limit=40, status="published")
        replied_note = None
        if replied_note_id:
            replied_note = await crud.get_note_by_id(session, replied_note_id)

    result = await process_user_message_async(
        raw_text=text,
        existing_notes=existing_notes,
        replied_note=replied_note,
        force_question=force_question
    )

    intent = result.get("intent", "create_note")

    if intent == "answer_question":
        answer = result.get("answer", "Не удалось найти информацию по этому вопросу.")
        related_id = result.get("related_note_id")
        keyboard = None
        if related_id:
            buttons = [
                InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit:{related_id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete:{related_id}"),
            ]
            if not any(x in settings.WEB_SITE_URL for x in ["localhost", "127.0.0.1"]):
                buttons.insert(0, InlineKeyboardButton(text="🌐 На сайте", url=f"{settings.WEB_SITE_URL}/#note-{related_id}"))
            keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])
        await message.answer(answer, reply_markup=keyboard, parse_mode="HTML")
        return

    # Create new note
    enhanced_text = result.get("enhanced_text") or text
    tags = result.get("tags") or []
    section = result.get("section") or "tasks"
    section_label = SECTION_LABELS.get(section, "Задачи и быт")

    async with async_session_factory() as session:
        note = await crud.create_note(
            session=session,
            text=enhanced_text,
            tags=tags,
            status="published",
            section=section
        )
        note_dict = note.to_dict()
        try:
            from bot.web.exporter import sync_site_async
            await sync_site_async(session)
        except Exception:
            pass

    # Real-time SSE push to open browser pages
    try:
        from bot.web.server import broadcast_sse
        await broadcast_sse("note_created", note_dict)
    except Exception:
        pass

    escaped_text = html.escape(note.text)
    response_text = f"📁 <b>{section_label}</b>\n\n{escaped_text}"
    buttons = [
        InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit:{note.id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete:{note.id}"),
    ]
    if not any(x in settings.WEB_SITE_URL for x in ["localhost", "127.0.0.1"]):
        buttons.insert(0, InlineKeyboardButton(text="🌐 На сайте", url=f"{settings.WEB_SITE_URL}/#note-{note.id}"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])
    await message.answer(response_text, reply_markup=keyboard, parse_mode="HTML")

