"""
Embedded aiohttp web server for Notes Garden.
Provides:
- Static HTML website serving (/ -> site/index.html)
- REST API (/api/notes, /api/stats)
- Server-Sent Events (/api/events) for instant real-time synchronization with Telegram bot
"""

import os
import json
import asyncio
import logging
from typing import Set, Optional
from aiohttp import web

from bot.config import settings
from bot.database.session import async_session_factory
from bot.database import crud
from bot.database.models import Note
from bot.utils import extract_tags
from bot.web.exporter import sync_site_async, SITE_DIR, INDEX_HTML_PATH

logger = logging.getLogger("notes_web_server")

@web.middleware
async def cors_middleware(request: web.Request, handler):
    """Enable CORS headers for cross-origin local access."""
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    return response


# Active SSE connected client response streams
_sse_clients: Set[web.StreamResponse] = set()
_web_runner: Optional[web.AppRunner] = None
_web_site: Optional[web.TCPSite] = None


async def broadcast_sse(event_type: str, data: dict):
    """
    Broadcast a real-time event to all connected browser clients via Server-Sent Events.
    """
    if not _sse_clients:
        return

    payload = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")
    dead_clients = set()

    for client in list(_sse_clients):
        try:
            await client.write(payload)
        except Exception:
            dead_clients.add(client)

    for dead in dead_clients:
        _sse_clients.discard(dead)


# --- HTTP Handlers ---

async def handle_index(request: web.Request) -> web.Response:
    """Serve site/index.html."""
    if os.path.exists(INDEX_HTML_PATH):
        return web.FileResponse(INDEX_HTML_PATH)
    return web.Response(text="site/index.html not found", status=404)


async def handle_get_notes(request: web.Request) -> web.Response:
    """
    GET /api/notes
    Query parameters:
    - tag: filter by tag
    - section: filter by section (games, movies, work, tasks, tech)
    - q: search query text
    - limit: integer (default 50)
    - offset: integer (default 0)
    - status: default 'published'
    """
    tag = request.query.get("tag")
    section = request.query.get("section")
    query = request.query.get("q")
    status = request.query.get("status", "published")
    try:
        limit = min(200, max(1, int(request.query.get("limit", 50))))
        offset = max(0, int(request.query.get("offset", 0)))
    except ValueError:
        limit, offset = 50, 0

    async with async_session_factory() as session:
        notes = await crud.get_notes(
            session=session,
            limit=limit,
            offset=offset,
            status=status,
            tag=tag,
            query=query,
            section=section
        )
        total = await crud.count_notes(session, status=status, query=query, tag=tag, section=section)

    return web.json_response({
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [n.to_dict() for n in notes]
    })


async def handle_get_note_by_id(request: web.Request) -> web.Response:
    """GET /api/notes/{id}"""
    try:
        note_id = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"error": "Invalid note id"}, status=400)

    async with async_session_factory() as session:
        note = await crud.get_note_by_id(session, note_id)

    if not note or note.status != "published":
        return web.json_response({"error": "Note not found"}, status=404)

    return web.json_response(note.to_dict())


async def handle_create_note(request: web.Request) -> web.Response:
    """
    POST /api/notes
    Create a new note from web client with AI enhancement and section classification.
    Payload: {"text": "...", "section": "..."}
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    text = (body.get("text") or "").strip()
    if not text:
        return web.json_response({"error": "Text cannot be empty"}, status=400)

    from bot.services.ai_enhancer import enhance_note_async
    enhanced = await enhance_note_async(text)
    saved_text = enhanced["enhanced_text"] if not body.get("raw") else text
    tags = body.get("tags") or enhanced["tags"]
    section = body.get("section") or enhanced.get("section") or "tasks"
    status = body.get("status", "published")

    async with async_session_factory() as session:
        note = await crud.create_note(
            session,
            text=saved_text,
            tags=tags,
            status=status,
            section=section
        )
        note_dict = note.to_dict()
        # Sync static file export
        await sync_site_async(session)

    # Broadcast real-time SSE event to all open browser windows
    await broadcast_sse("note_created", note_dict)

    return web.json_response(note_dict, status=201)


async def handle_classify_ai(request: web.Request) -> web.Response:
    """
    POST /api/ai/classify
    Directly classify any text into a section using AI.
    Payload: {"text": "..."}
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    text = (body.get("text") or "").strip()
    if not text:
        return web.json_response({"error": "Text is required"}, status=400)

    from bot.services.ai_enhancer import classify_section_async, SECTION_LABELS
    sec = await classify_section_async(text)
    return web.json_response({
        "section": sec,
        "label": SECTION_LABELS.get(sec, "Задачи и быт")
    })


async def handle_reclassify_notes(request: web.Request) -> web.Response:
    """
    POST /api/notes/reclassify
    Runs AI classification over existing notes to distribute them into sections.
    """
    force_all = request.query.get("all") == "true"
    from bot.services.ai_enhancer import classify_section_async, SECTION_LABELS

    updated_count = 0
    results = []

    async with async_session_factory() as session:
        notes = await crud.get_notes(session, limit=1000, offset=0, status=None)
        for note in notes:
            if force_all or not note.section:
                sec = await classify_section_async(f"{note.text} {' '.join(note.tags or [])}")
                note.section = sec
                updated_count += 1
                results.append({
                    "id": note.id,
                    "section": sec,
                    "label": SECTION_LABELS.get(sec, sec)
                })
        if updated_count > 0:
            await session.commit()
            await sync_site_async(session)

    return web.json_response({
        "message": f"Successfully reclassified {updated_count} notes with AI",
        "updated": updated_count,
        "items": results
    })


async def handle_get_stats(request: web.Request) -> web.Response:
    """
    GET /api/stats
    Returns aggregated stats on notes and tags.
    """
    async with async_session_factory() as session:
        total_notes = await crud.count_notes(session, status="published")
        tags_dict = await crud.get_tags_with_counts(session, status="published")

    return web.json_response({
        "total_notes": total_notes,
        "total_tags": len(tags_dict),
        "tags": tags_dict
    })


async def handle_sse_events(request: web.Request) -> web.StreamResponse:
    """
    GET /api/events
    Server-Sent Events endpoint.
    Keeps connection open to stream real-time note updates to the browser.
    """
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }
    )
    await response.prepare(request)

    _sse_clients.add(response)
    logger.info(f"SSE client connected. Active connections: {len(_sse_clients)}")

    # Send initial greeting event
    try:
        welcome_payload = f"event: connected\ndata: {json.dumps({'status': 'ready'})}\n\n".encode("utf-8")
        await response.write(welcome_payload)

        # Keep connection alive with periodic heartbeats
        while True:
            await asyncio.sleep(25)
            ping_payload = b": ping\n\n"
            await response.write(ping_payload)
    except (asyncio.CancelledError, ConnectionResetError, Exception):
        pass
    finally:
        _sse_clients.discard(response)
        logger.info(f"SSE client disconnected. Active connections: {len(_sse_clients)}")

    return response


def create_web_app() -> web.Application:
    """Build and configure the aiohttp application."""
    app = web.Application(middlewares=[cors_middleware])

    # Route registrations
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/notes", handle_get_notes)
    app.router.add_get("/api/notes/{id:\\d+}", handle_get_note_by_id)
    app.router.add_post("/api/notes", handle_create_note)
    app.router.add_post("/api/notes/reclassify", handle_reclassify_notes)
    app.router.add_post("/api/ai/classify", handle_classify_ai)
    app.router.add_get("/api/stats", handle_get_stats)
    app.router.add_get("/api/events", handle_sse_events)

    # Static assets fallback (for notes.json and any other static files)
    if os.path.exists(SITE_DIR):
        app.router.add_static("/static/", SITE_DIR, show_index=False)
        # Direct static file serving for files in /site
        async def static_site_file(request):
            filename = request.match_info.get("filename", "")
            filepath = os.path.join(SITE_DIR, filename)
            if os.path.isfile(filepath):
                return web.FileResponse(filepath)
            raise web.HTTPNotFound()
        app.router.add_get("/{filename:[^/]+\\.(json|css|js|svg|png|ico)}", static_site_file)

    return app


async def start_web_server(host: Optional[str] = None, port: Optional[int] = None) -> web.AppRunner:
    """Start the web server in the current asyncio loop."""
    global _web_runner, _web_site
    app = create_web_app()
    _web_runner = web.AppRunner(app)
    await _web_runner.setup()

    env_host = os.environ.get("WEB_SERVER_HOST") or os.environ.get("HOST")
    server_host = host or env_host or settings.WEB_SERVER_HOST

    env_port = os.environ.get("PORT")
    if env_port and env_port.isdigit():
        server_port = int(env_port)
    else:
        server_port = port or settings.WEB_SERVER_PORT

    _web_site = web.TCPSite(_web_runner, server_host, server_port)
    await _web_site.start()
    logger.info(f"🌿 Notes Garden Web Server running at http://{server_host}:{server_port}")
    return _web_runner


async def stop_web_server():
    """Cleanly stop the web server and close client connections."""
    global _web_runner, _web_site
    for client in list(_sse_clients):
        try:
            await client.write_eof()
        except Exception:
            pass
    _sse_clients.clear()

    if _web_runner:
        await _web_runner.cleanup()
        _web_runner = None
        _web_site = None
        logger.info("Notes Garden Web Server stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    async def standalone_run():
        await start_web_server()
        print(f"Notes Garden web server running on http://{settings.WEB_SERVER_HOST}:{settings.WEB_SERVER_PORT}")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            await stop_web_server()

    asyncio.run(standalone_run())
