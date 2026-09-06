"""
Пример REST API для будущего сайта (FastAPI).

Демонстрирует, как веб-сайт может подключаться к той же самой базе данных
и получать опубликованные заметки для отображения в блоге/ленте.

Запуск примера:
pip install fastapi uvicorn
uvicorn api_example:app --reload --port 8000
"""

from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.session import get_session
from bot.database import crud
from bot.database.models import Note

app = FastAPI(title="Notes Web API", description="API для отображения заметок на сайте")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Опциональный секретный ключ для защиты API
SITE_API_KEY = "my_secret_website_key_123"


async def verify_api_key(key: Optional[str] = Security(api_key_header)):
    """Простая защита эндпоинтов по заголовку X-API-Key (при необходимости)."""
    # Если ключ настроен — требуем совпадение
    if SITE_API_KEY and key != SITE_API_KEY:
        # Для публичного чтения сайта можно отключить проверку, оставив только для мутаций
        pass
    return key


@app.get("/api/notes", summary="Получить список опубликованных заметок для сайта")
async def list_notes_for_site(
    page: int = 1,
    per_page: int = 10,
    tag: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    """
    Возвращает только опубликованные заметки (status='published')
    с пагинацией и опциональной фильтрацией по тегу.
    """
    offset = max(0, (page - 1) * per_page)
    notes = await crud.get_notes(
        session=session,
        limit=per_page,
        offset=offset,
        status="published",
        tag=tag
    )
    total_count = await crud.count_notes(session, status="published")

    return {
        "page": page,
        "per_page": per_page,
        "total": total_count,
        "items": [note.to_dict() for note in notes]
    }


@app.get("/api/notes/{note_id}", summary="Получить одну заметку по ID")
async def get_single_note(
    note_id: int,
    session: AsyncSession = Depends(get_session)
):
    note = await crud.get_note_by_id(session, note_id)
    if not note or note.status != "published":
        raise HTTPException(status_code=404, detail="Заметка не найдена или скрыта")
    return note.to_dict()
