from typing import List, Optional
from sqlalchemy import select, func, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Note


async def create_note(
    session: AsyncSession,
    text: str,
    tags: List[str],
    status: str = "published",
    section: Optional[str] = None
) -> Note:
    """Create and save a new note."""
    note = Note(
        text=text,
        tags=tags,
        status=status,
        section=section
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


async def get_note_by_id(session: AsyncSession, note_id: int) -> Optional[Note]:
    """Retrieve a single note by primary key ID."""
    stmt = select(Note).where(Note.id == note_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


from sqlalchemy import text


def _apply_tag_filter(stmt, tag: Optional[str]):
    """Apply SQL-level JSON array tag filtering compatible with SQLite and Postgres."""
    if not tag:
        return stmt
    tag_clean = tag.lower().lstrip("#")
    return stmt.where(
        text("EXISTS (SELECT 1 FROM json_each(notes.tags) WHERE lower(value) = :tag_filter)")
    ).params(tag_filter=tag_clean)


async def get_notes(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    query: Optional[str] = None,
    section: Optional[str] = None
) -> List[Note]:
    """Fetch paginated notes, optionally filtered by status, tag, section or text search query."""
    stmt = select(Note).order_by(desc(Note.id))
    if status is not None:
        stmt = stmt.where(Note.status == status)
    if section and section != "all":
        stmt = stmt.where(Note.section == section)
    if query:
        search_pattern = f"%{query.strip()}%"
        stmt = stmt.where(Note.text.ilike(search_pattern))
    stmt = _apply_tag_filter(stmt, tag)

    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    notes = list(result.scalars().all())
    return notes


async def count_notes(
    session: AsyncSession,
    status: Optional[str] = None,
    query: Optional[str] = None,
    tag: Optional[str] = None,
    section: Optional[str] = None
) -> int:
    """Get total count of notes matching criteria, including tag and section filtering."""
    stmt = select(func.count(Note.id))
    if status is not None:
        stmt = stmt.where(Note.status == status)
    if section and section != "all":
        stmt = stmt.where(Note.section == section)
    if query:
        search_pattern = f"%{query.strip()}%"
        stmt = stmt.where(Note.text.ilike(search_pattern))
    stmt = _apply_tag_filter(stmt, tag)
    result = await session.execute(stmt)
    return result.scalar() or 0


async def get_tags_with_counts(session: AsyncSession, status: str = "published") -> dict:
    """Extract all tags and their occurrence counts for active notes."""
    stmt = select(Note.tags).where(Note.status == status)
    result = await session.execute(stmt)
    tag_counts = {}
    for (tags_list,) in result.all():
        if isinstance(tags_list, list):
            for t in tags_list:
                cleaned = str(t).strip().lstrip("#").lower()
                if cleaned:
                    tag_counts[cleaned] = tag_counts.get(cleaned, 0) + 1
    # Sort tags by frequency descending
    return dict(sorted(tag_counts.items(), key=lambda item: item[1], reverse=True))



async def update_note_text(
    session: AsyncSession,
    note_id: int,
    new_text: str,
    new_tags: List[str]
) -> Optional[Note]:
    """Update text and tags for a note."""
    note = await get_note_by_id(session, note_id)
    if not note:
        return None
    note.text = new_text
    note.tags = new_tags
    await session.commit()
    await session.refresh(note)
    return note


async def update_note_status(
    session: AsyncSession,
    note_id: int,
    new_status: str
) -> Optional[Note]:
    """Update publication status for a note ('published', 'hidden', 'draft')."""
    note = await get_note_by_id(session, note_id)
    if not note:
        return None
    note.status = new_status
    await session.commit()
    await session.refresh(note)
    return note


async def delete_note(session: AsyncSession, note_id: int) -> bool:
    """Delete a note by ID."""
    stmt = delete(Note).where(Note.id == note_id)
    result = await session.execute(stmt)
    await session.commit()
    return (result.rowcount or 0) > 0


async def update_note_section(
    session: AsyncSession,
    note_id: int,
    section: str
) -> Optional[Note]:
    """Update section category for a note."""
    note = await get_note_by_id(session, note_id)
    if not note:
        return None
    note.section = section
    await session.commit()
    await session.refresh(note)
    return note

