import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from bot.database.session import async_session_factory
from bot.database import crud
from bot.utils import extract_tags, format_note_card, format_notes_list


async def smoke_test():
    print("=== 1. Testing tag extraction ===")
    sample_text = "Тестовая заметка с тегами #идея #проект_1 #AI_2026 #apple-design #seo-geo #react-bits #theme-factory #чётко!"
    tags = extract_tags(sample_text)
    print(f"Extracted tags: {tags}")
    assert "идея" in tags, "Cyrillic tag failed"
    assert "проект_1" in tags, "Underscore tag failed"
    assert "AI_2026" in tags, "Alphanumeric tag failed"
    assert "apple-design" in tags, "Hyphenated tag apple-design failed"
    assert "seo-geo" in tags, "Hyphenated tag seo-geo failed"
    assert "react-bits" in tags, "Hyphenated tag react-bits failed"
    assert "theme-factory" in tags, "Hyphenated tag theme-factory failed"
    assert "чётко" in tags, "Cyrillic 'ё' tag failed"
    print("Tag extraction: PASSED ✅")

    print("\n=== 2. Testing Database CRUD ===")
    async with async_session_factory() as session:
        # Create
        note = await crud.create_note(session, sample_text, tags, status="published")
        note_id = note.id
        print(f"Created note #{note_id}: status={note.status}, tags={note.tags}")
        assert note_id > 0

        # Read
        fetched = await crud.get_note_by_id(session, note_id)
        assert fetched is not None
        assert fetched.text == sample_text

        # Format Card
        card = format_note_card(fetched)
        assert f"Заметка №{note_id}" in card
        print(f"Formatted card preview:\n{card[:120]}...")

        # Update text & tags
        new_text = "Обновленный текст #новости"
        new_tags = extract_tags(new_text)
        updated = await crud.update_note_text(session, note_id, new_text, new_tags)
        assert updated.text == new_text
        assert updated.tags == ["новости"]
        print(f"Updated note #{note_id} text and tags")

        # Update status
        hidden = await crud.update_note_status(session, note_id, "hidden")
        assert hidden.status == "hidden"
        print(f"Updated status to 'hidden'")

        # Count
        cnt = await crud.count_notes(session)
        assert cnt >= 1
        print(f"Count notes: {cnt}")

        # List
        notes = await crud.get_notes(session, limit=5, offset=0)
        assert len(notes) >= 1
        list_view = format_notes_list(notes, page=0, total_count=cnt, per_page=5)
        assert f"№{note_id}" in list_view
        print("List view: PASSED ✅")

        # Delete
        deleted = await crud.delete_note(session, note_id)
        assert deleted is True
        fetched_after = await crud.get_note_by_id(session, note_id)
        assert fetched_after is None
        print(f"Deleted note #{note_id}: PASSED ✅")

    print("\nALL SMOKE TESTS PASSED! 🎉")


if __name__ == "__main__":
    asyncio.run(smoke_test())
