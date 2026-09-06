from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.models import Note


def get_note_action_keyboard(note: Note) -> InlineKeyboardMarkup:
    """Inline keyboard for a specific note."""
    status_btn_text = "👁 Скрыть" if note.status == "published" else "📢 Опубликовать"

    keyboard = [
        [
            InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit:{note.id}"),
            InlineKeyboardButton(text=status_btn_text, callback_data=f"toggle_status:{note.id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete:{note.id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_delete_confirm_keyboard(note_id: int) -> InlineKeyboardMarkup:
    """Confirmation inline keyboard before deleting a note."""
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete:{note_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_pagination_keyboard(
    current_page: int,
    total_pages: int,
    notes: list[Note]
) -> InlineKeyboardMarkup:
    """Pagination keyboard for notes list with note quick action buttons."""
    keyboard = []

    # Quick buttons to view/manage each note on current page
    note_buttons = []
    for note in notes:
        note_buttons.append(
            InlineKeyboardButton(text=f"№{note.id}", callback_data=f"view:{note.id}")
        )
    # Split into rows of max 5 buttons
    for i in range(0, len(note_buttons), 5):
        keyboard.append(note_buttons[i:i + 5])

    # Navigation row
    nav_row = []
    if current_page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page:{current_page - 1}")
        )

    nav_row.append(
        InlineKeyboardButton(
            text=f"Стр. {current_page + 1}/{max(1, total_pages)}",
            callback_data="noop"
        )
    )

    if current_page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"page:{current_page + 1}")
        )

    keyboard.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Simple cancel button."""
    keyboard = [
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_action")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
