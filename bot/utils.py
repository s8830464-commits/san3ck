import html
import re
from typing import List
from bot.database.models import Note

STATUS_EMOJIS = {
    "published": "🟢 Опубликовано",
    "hidden": "👁 Скрыто",
    "draft": "📝 Черновик"
}


def extract_tags(text: str) -> List[str]:
    """
    Extract hashtag names from text, e.g. #python, #заметка_1, #apple-design, #seo-geo.
    Supports latin, cyrillic (including ё/Ё), numbers, underscores, and internal hyphens.
    """
    matches = re.findall(r"#([a-zA-Zа-яА-ЯёЁ0-9_]+(?:-[a-zA-Zа-яА-ЯёЁ0-9_]+)*)", text)
    seen = set()
    tags = []
    for tag in matches:
        tag_clean = tag.strip()
        if tag_clean and tag_clean.lower() not in seen:
            seen.add(tag_clean.lower())
            tags.append(tag_clean)
    return tags


def format_note_card(note: Note) -> str:
    """Format a single note card with metadata and body using safe HTML."""
    status_label = STATUS_EMOJIS.get(note.status, note.status)
    created_str = note.created_at.strftime("%d.%m.%Y %H:%M") if note.created_at else "–"
    
    tags_str = " ".join([f"#{html.escape(t)}" for t in (note.tags or [])])
    if not tags_str:
        tags_str = "<i>нет</i>"

    escaped_text = html.escape(note.text)
    return (
        f"📝 <b>Заметка №{note.id}</b>\n"
        f"📅 <b>Создана:</b> {created_str}\n"
        f"📊 <b>Статус:</b> {status_label}\n"
        f"🏷 <b>Теги:</b> {tags_str}\n"
        f"────────────────────\n"
        f"{escaped_text}"
    )


def format_notes_list(notes: List[Note], page: int, total_count: int, per_page: int) -> str:
    """Format a list of notes with snippets for paginated view using safe HTML."""
    if not notes:
        return "📭 У вас пока нет сохранённых заметок. Просто отправьте текст, чтобы создать первую!"

    total_pages = (total_count + per_page - 1) // per_page
    lines = [f"📋 <b>Ваши заметки</b> (всего: {total_count}, стр. {page + 1}/{max(1, total_pages)}):\n"]

    for note in notes:
        status_icon = "🟢" if note.status == "published" else ("👁" if note.status == "hidden" else "📝")
        created_str = note.created_at.strftime("%d.%m %H:%M") if note.created_at else ""
        
        snippet = note.text.strip().replace("\n", " ")
        if len(snippet) > 60:
            snippet = snippet[:57] + "..."
        snippet = html.escape(snippet)

        tags_snippet = ""
        if note.tags:
            tags_snippet = " [" + " ".join([f"#{html.escape(t)}" for t in note.tags[:3]]) + "]"

        lines.append(f"<b>№{note.id}</b> {status_icon} <code>{created_str}</code>: {snippet}{tags_snippet}")

    lines.append("\n<i>Нажмите на кнопку с номером заметки ниже, чтобы открыть её и изменить.</i>")
    return "\n".join(lines)
