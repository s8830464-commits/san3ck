"""
Static site exporter for Notes Garden.
Synchronizes SQLite database notes with static HTML and JSON artifacts in the /site directory,
ensuring the website is functional both through the web server and directly as a local file (file:///).
"""

import json
import os
import re
import logging
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database import crud
from bot.database.models import Note

logger = logging.getLogger("notes_exporter")

SITE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "site"))
INDEX_HTML_PATH = os.path.join(SITE_DIR, "index.html")
NOTES_JSON_PATH = os.path.join(SITE_DIR, "notes.json")


def export_site(notes_data: List[Dict]) -> bool:
    """
    Write notes to site/notes.json and embed them into site/index.html.
    This guarantees that opening site/index.html directly in a browser
    works with all notes visible even without an HTTP server running.
    """
    try:
        os.makedirs(SITE_DIR, exist_ok=True)

        # 1. Save notes.json
        payload = {
            "total": len(notes_data),
            "items": notes_data
        }
        with open(NOTES_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # 2. Inject initial notes into index.html if it exists
        if os.path.exists(INDEX_HTML_PATH):
            with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
                content = f.read()

            raw_json = json.dumps(notes_data, ensure_ascii=False)
            # Prevent premature </script> tag termination in HTML
            safe_json = raw_json.replace("</script>", "<\\/script>").replace("</Script>", "<\\/Script>")

            # Check for <script id="initialNotesData" ...>...</script>
            json_script_pattern = r'<script id="initialNotesData"[^>]*>.*?</script>'
            if re.search(json_script_pattern, content, flags=re.DOTALL):
                replacement = f'<script id="initialNotesData" type="application/json">\n{safe_json}\n  </script>'
                # Crucial: Use lambda to prevent re.sub from processing backslashes/newlines as escape sequences
                # and count=1 to guarantee only the designated script tag is replaced
                new_content = re.sub(json_script_pattern, lambda m: replacement, content, count=1, flags=re.DOTALL)
                with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
                    f.write(new_content)
                logger.info(f"Successfully injected {len(notes_data)} notes into {INDEX_HTML_PATH}")
            else:
                # Fallback for window.__INITIAL_NOTES__ = [...];
                legacy_pattern = r'window\.__INITIAL_NOTES__\s*=\s*\[.*?\];'
                replacement = f'window.__INITIAL_NOTES__ = {safe_json};'
                new_content, count = re.subn(legacy_pattern, lambda m: replacement, content, flags=re.DOTALL)
                if count > 0:
                    with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    logger.info(f"Successfully injected {len(notes_data)} notes into {INDEX_HTML_PATH}")
                else:
                    logger.warning("Could not find initial notes script pattern in index.html")

        return True
    except Exception as e:
        logger.error(f"Error exporting site: {e}", exc_info=True)
        return False


async def sync_site_async(session: AsyncSession) -> bool:
    """
    Fetch all published notes from the database and export the site.
    """
    try:
        notes = await crud.get_notes(session, limit=1000, offset=0, status="published")
        notes_dict_list = [n.to_dict() for n in notes]
        success = export_site(notes_dict_list)
        return success
    except Exception as e:
        logger.error(f"Failed to sync site from database: {e}", exc_info=True)
        return False
