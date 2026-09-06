import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from aiohttp.test_utils import TestClient, TestServer
from bot.web.server import create_web_app
from bot.database.session import async_session_factory
from bot.database import crud
from bot.web.exporter import sync_site_async, INDEX_HTML_PATH, NOTES_JSON_PATH


async def test_web_server_and_api():
    print("\n=== 1. Testing Web Server & Endpoints ===")
    app = create_web_app()
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        # Test index page
        res = await client.get("/")
        assert res.status == 200, f"Expected 200, got {res.status}"
        html = await res.text()
        assert "Notes Garden" in html
        assert " Личный сад мыслей и заметок" in html
        print("GET / [Index HTML]: PASSED ✅")

        # Test GET /api/notes
        res = await client.get("/api/notes?limit=10")
        assert res.status == 200
        notes_data = await res.json()
        assert "items" in notes_data
        assert "total" in notes_data
        assert notes_data["total"] > 0
        assert len(notes_data["items"]) <= 10
        print(f"GET /api/notes: PASSED ✅ (Found {notes_data['total']} notes)")

        # Test filtering by tag
        res = await client.get("/api/notes?tag=дизайн")
        assert res.status == 200
        tag_filtered = await res.json()
        assert len(tag_filtered["items"]) > 0
        for item in tag_filtered["items"]:
            assert any(t.lower() == "дизайн" for t in item["tags"])
        print(f"GET /api/notes?tag=дизайн: PASSED ✅ ({len(tag_filtered['items'])} items)")

        # Test filtering by hyphenated tags
        for domain_tag in ["boost", "seo-geo", "react-bits", "goal"]:
            res = await client.get(f"/api/notes?tag={domain_tag}")
            assert res.status == 200
            d_filtered = await res.json()
            assert len(d_filtered["items"]) > 0
            assert d_filtered["total"] >= len(d_filtered["items"])
            for item in d_filtered["items"]:
                assert any(t.lower() == domain_tag.lower() for t in item["tags"])
            print(f"GET /api/notes?tag={domain_tag}: PASSED ✅ ({len(d_filtered['items'])} items)")

        # Test search query
        res = await client.get("/api/notes?q=Apple")
        assert res.status == 200
        search_res = await res.json()
        assert len(search_res["items"]) > 0
        print(f"GET /api/notes?q=Apple: PASSED ✅ ({len(search_res['items'])} items)")

        # Test GET /api/stats
        res = await client.get("/api/stats")
        assert res.status == 200
        stats = await res.json()
        assert stats["total_notes"] > 0
        assert stats["total_tags"] > 0
        assert "дизайн" in stats["tags"]
        print(f"GET /api/stats: PASSED ✅ ({stats['total_notes']} notes, {stats['total_tags']} tags)")

        # Test POST /api/notes
        test_payload = {
            "text": "Проверка создания заметки через веб-сервер #тест #web_test"
        }
        res = await client.post("/api/notes", json=test_payload)
        assert res.status == 201
        created = await res.json()
        note_id = created["id"]
        assert note_id > 0
        assert "тест" in created["tags"]
        assert "web_test" in created["tags"]
        print(f"POST /api/notes: PASSED ✅ (Created note #{note_id})")

        # Clean up created test note
        async with async_session_factory() as session:
            await crud.delete_note(session, note_id)
            await sync_site_async(session)
        print(f"Cleanup test note #{note_id}: PASSED ✅")

        # Verify static exporter generated files
        assert os.path.exists(INDEX_HTML_PATH)
        assert os.path.exists(NOTES_JSON_PATH)
        with open(NOTES_JSON_PATH, "r", encoding="utf-8") as f:
            jdata = json.load(f)
            assert jdata["total"] > 0
        print("Static files (index.html & notes.json) verification: PASSED ✅")

    finally:
        await client.close()

    print("\nALL WEB SERVER TESTS PASSED! 🎉\n")


if __name__ == "__main__":
    asyncio.run(test_web_server_and_api())
