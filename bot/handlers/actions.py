import html
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from bot.database.session import async_session_factory
from bot.database import crud
from bot.keyboards.inline import (
    get_delete_confirm_keyboard,
    get_note_action_keyboard,
)
from bot.utils import format_note_card

router = Router(name="actions_router")


@router.message(Command("delete"))
async def cmd_delete_note(message: Message):
    """Handle /delete <id> command."""
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Пожалуйста, укажите ID заметки: <code>/delete &lt;id&gt;</code>\nНапример: <code>/delete 1</code>", parse_mode="HTML")
        return

    note_id = int(args[1])
    async with async_session_factory() as session:
        note = await crud.get_note_by_id(session, note_id)

    if not note:
        await message.answer(f"❌ Заметка с ID №{note_id} не найдена.")
        return

    snippet = html.escape(note.text[:100])
    await message.answer(
        f"❓ Вы действительно хотите удалить заметку <b>№{note_id}</b>?\n<i>{snippet}</i>",
        reply_markup=get_delete_confirm_keyboard(note_id),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("delete:"))
async def cb_delete_prompt(callback: CallbackQuery):
    """Handle delete button click by prompting confirmation."""
    note_id = int(callback.data.split(":")[1])
    async with async_session_factory() as session:
        note = await crud.get_note_by_id(session, note_id)

    if not note:
        await callback.answer("❌ Заметка не найдена.", show_alert=True)
        return

    snippet = html.escape(note.text[:100])
    await callback.message.answer(
        f"❓ Вы действительно хотите удалить заметку <b>№{note_id}</b>?\n<i>{snippet}</i>",
        reply_markup=get_delete_confirm_keyboard(note_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_confirm_delete(callback: CallbackQuery):
    """Confirm and execute note deletion."""
    note_id = int(callback.data.split(":")[1])
    async with async_session_factory() as session:
        deleted = await crud.delete_note(session, note_id)
        if deleted:
            try:
                from bot.web.exporter import sync_site_async
                await sync_site_async(session)
            except Exception:
                pass

    if deleted:
        try:
            from bot.web.server import broadcast_sse
            await broadcast_sse("note_deleted", {"id": note_id})
        except Exception:
            pass

        await callback.message.edit_text(
            f"🗑 <b>Заметка №{note_id} была успешно удалена.</b>",
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text("❌ Заметка уже была удалена ранее.")
    await callback.answer()


@router.callback_query(F.data == "cancel_action")
async def cb_cancel_action(callback: CallbackQuery, state: FSMContext):
    """Cancel ongoing operation (edit, delete, etc.)."""
    current_state = await state.get_state()
    if current_state:
        await state.clear()

    try:
        await callback.message.edit_text("🚫 Действие отменено.")
    except Exception:
        await callback.message.delete()
    await callback.answer("Отменено")


@router.message(Command("hide"))
async def cmd_hide_note(message: Message):
    """Handle /hide <id> command."""
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Пожалуйста, укажите ID заметки: <code>/hide &lt;id&gt;</code>", parse_mode="HTML")
        return

    note_id = int(args[1])
    async with async_session_factory() as session:
        note = await crud.update_note_status(session, note_id, new_status="hidden")
        if note:
            try:
                from bot.web.exporter import sync_site_async
                await sync_site_async(session)
            except Exception:
                pass

    if not note:
        await message.answer(f"❌ Заметка №{note_id} не найдена.")
        return

    try:
        from bot.web.server import broadcast_sse
        await broadcast_sse("note_updated", note.to_dict())
    except Exception:
        pass

    await message.answer(
        f"👁 <b>Заметка №{note_id} скрыта</b> (не будет видна на сайте).\n\n" + format_note_card(note),
        reply_markup=get_note_action_keyboard(note),
        parse_mode="HTML"
    )


@router.message(Command("show"))
async def cmd_show_note(message: Message):
    """Handle /show <id> command."""
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Пожалуйста, укажите ID заметки: <code>/show &lt;id&gt;</code>", parse_mode="HTML")
        return

    note_id = int(args[1])
    async with async_session_factory() as session:
        note = await crud.update_note_status(session, note_id, new_status="published")
        if note:
            try:
                from bot.web.exporter import sync_site_async
                await sync_site_async(session)
            except Exception:
                pass

    if not note:
        await message.answer(f"❌ Заметка №{note_id} не найдена.")
        return

    try:
        from bot.web.server import broadcast_sse
        await broadcast_sse("note_updated", note.to_dict())
    except Exception:
        pass

    await message.answer(
        f"📢 <b>Заметка №{note_id} опубликована</b> (будет видна на сайте).\n\n" + format_note_card(note),
        reply_markup=get_note_action_keyboard(note),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("toggle_status:"))
async def cb_toggle_status(callback: CallbackQuery):
    """Toggle status between published and hidden."""
    note_id = int(callback.data.split(":")[1])
    async with async_session_factory() as session:
        note = await crud.get_note_by_id(session, note_id)
        if not note:
            await callback.answer("❌ Заметка не найдена.", show_alert=True)
            return

        new_status = "hidden" if note.status == "published" else "published"
        updated_note = await crud.update_note_status(session, note_id, new_status)
        if updated_note:
            try:
                from bot.web.exporter import sync_site_async
                await sync_site_async(session)
            except Exception:
                pass

    if updated_note:
        try:
            from bot.web.server import broadcast_sse
            await broadcast_sse("note_updated", updated_note.to_dict())
        except Exception:
            pass

    alert_text = "👁 Заметка скрыта" if new_status == "hidden" else "📢 Заметка опубликована"
    await callback.answer(alert_text)

    try:
        await callback.message.edit_text(
            format_note_card(updated_note),
            reply_markup=get_note_action_keyboard(updated_note),
            parse_mode="HTML"
        )
    except Exception:
        pass

