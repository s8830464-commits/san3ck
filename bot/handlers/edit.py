import html
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from bot.database.session import async_session_factory
from bot.database import crud
from bot.states.note_states import EditNoteState
from bot.keyboards.inline import get_note_action_keyboard, get_cancel_keyboard
from bot.utils import extract_tags, format_note_card

router = Router(name="edit_router")


@router.message(Command("edit"))
async def cmd_edit_note(message: Message, state: FSMContext):
    """Handle /edit <id> command."""
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Пожалуйста, укажите ID заметки: <code>/edit &lt;id&gt;</code>\nНапример: <code>/edit 1</code>", parse_mode="HTML")
        return

    note_id = int(args[1])
    async with async_session_factory() as session:
        note = await crud.get_note_by_id(session, note_id)

    if not note:
        await message.answer(f"❌ Заметка с ID №{note_id} не найдена.")
        return

    await state.set_state(EditNoteState.waiting_for_new_text)
    await state.update_data(note_id=note_id)

    escaped_prev = html.escape(note.text)
    prompt = (
        f"✏️ <b>Редактирование заметки №{note_id}</b>\n\n"
        f"Текущий текст:\n<i>{escaped_prev}</i>\n\n"
        f"Отправьте следующим сообщением <b>новый текст</b> заметки:"
    )
    await message.answer(prompt, reply_markup=get_cancel_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("edit:"))
async def cb_edit_note(callback: CallbackQuery, state: FSMContext):
    """Handle inline button edit:<id>."""
    note_id = int(callback.data.split(":")[1])
    async with async_session_factory() as session:
        note = await crud.get_note_by_id(session, note_id)

    if not note:
        await callback.answer("❌ Заметка не найдена.", show_alert=True)
        return

    await state.set_state(EditNoteState.waiting_for_new_text)
    await state.update_data(note_id=note_id)

    escaped_prev = html.escape(note.text)
    prompt = (
        f"✏️ <b>Редактирование заметки №{note_id}</b>\n\n"
        f"Текущий текст:\n<i>{escaped_prev}</i>\n\n"
        f"Отправьте следующим сообщением <b>новый текст</b> заметки:"
    )
    await callback.message.answer(prompt, reply_markup=get_cancel_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.message(EditNoteState.waiting_for_new_text, F.text)
async def process_new_note_text(message: Message, state: FSMContext):
    """Receive new text for the note and save changes."""
    data = await state.get_data()
    note_id = data.get("note_id")
    new_text = message.text.strip()

    if not new_text:
        await message.answer("⚠️ Текст заметки не может быть пустым.")
        return

    new_tags = extract_tags(new_text)

    async with async_session_factory() as session:
        updated_note = await crud.update_note_text(
            session=session,
            note_id=note_id,
            new_text=new_text,
            new_tags=new_tags
        )
        if updated_note:
            try:
                from bot.web.exporter import sync_site_async
                await sync_site_async(session)
            except Exception:
                pass

    await state.clear()

    if not updated_note:
        await message.answer("❌ Не удалось обновить заметку (возможно, она была удалена).")
        return

    try:
        from bot.web.server import broadcast_sse
        await broadcast_sse("note_updated", updated_note.to_dict())
    except Exception:
        pass

    response_text = "✨ <b>Заметка успешно обновлена на сайте!</b>\n\n" + format_note_card(updated_note)
    keyboard = get_note_action_keyboard(updated_note)
    await message.answer(response_text, reply_markup=keyboard, parse_mode="HTML")

