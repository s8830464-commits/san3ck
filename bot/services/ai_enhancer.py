"""
AI Enhancer module for Note processing.
Supports both free modern LLM APIs (Groq, Google Gemini, OpenRouter)
and a built-in intelligent NLP fallback engine.
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
import aiohttp

from bot.config import settings

logger = logging.getLogger("ai_enhancer")

VALID_SECTIONS = {"games", "movies", "work", "tasks", "tech"}

SECTION_LABELS = {
    "games": "Игры",
    "movies": "Фильмы",
    "work": "Работа",
    "tasks": "Задачи и быт",
    "tech": "Технологии",
}

SYSTEM_PROMPT = """Ты — персональный умный AI-ассистент для ведения заметок FastNotes в премиальном стиле Apple.
Пользователь отправляет тебе мысль, идею, план, задачу или заметку (часто на ходу, кратко или с опечатками).

Твоя задача — превратить входящую мысль в полноценную, содержательную и структурированную заметку. Заметка не должна быть куцей или состоять из одного короткого пункта — раскрой её информативно, полезно и красиво.

СТРУКТУРА ЗАМЕТКИ (поле "enhanced_text"):
1. Чёткий, ёмкий заголовок.
2. Краткое описание или контекст цели/задачи (1–2 предложения, объясняющие суть).
3. Список из 3–4 конкретных, содержательных подпунктов (с маркером «•»):
   - Ключевые шаги выполнения и этапы
   - Критерии готовности или важные требования
   - Подзадачи, нюансы или дедлайны
4. СТРОГО БЕЗ ЭМОДЗИ! Не используй смайлики, пиктограммы или эмодзи. Только красивый чистый текст и маркеры «•».
5. ХЭШТЕГИ НЕ НУЖНЫ: оставь поле "tags" пустым массивом [].
6. ОПРЕДЕЛИТЬ РАЗДЕЛ (поле "section"):
   - "games" (Игры: видеоигры, консоли, Steam, Forza Horizon, гейминг)
   - "movies" (Фильмы: кино, фильмы, сериалы, сеансы, кинотеатр)
   - "work" (Работа и проекты: проекты, учеба, цели, клиенты, договоры, баллы, дедлайны)
   - "tasks" (Задачи и быт: быт, стирка, уборка, покупки, дом, здоровье, личные дела)
   - "tech" (Технологии: программирование, IT, код, боты, Python, AI, сайты, серверы)
   Если нет однозначного соответствия, выбери наиболее близкий или "tasks".
7. Поле "friendly_reply": ультра-краткий ответ (1-3 слова, например: «Сохранено.»).

Пример:
Вход: "получить 100 баллов за этот проект"
Выход:
{
  "enhanced_text": "Цель проекта: Максимальный балл\\n\\nСтратегия успешной реализации проекта и получение максимальной оценки (100 баллов).\\n\\n• Проверить соответствие всем техническим требованиям и критериям приёмки\\n• Провести финальное тестирование функционала и устранить критические замечания\\n• Подготовить наглядную демонстрацию и документацию по работе системы\\n• Защитить проект в срок, акцентируя внимание на ключевых преимуществах",
  "tags": [],
  "section": "work",
  "friendly_reply": "Сохранено."
}

Отвечай СТРОГО валидным JSON-объектом указанной структуры без лишнего текста до и после."""

# Fallback command words to strip
COMMAND_WORDS = [
    r"\bсахрони\b", r"\bсохрани\b", r"\bсохранить\b",
    r"\bзапиши\b", r"\bзаписать\b", r"\bзапомни\b",
    r"\bнапомни\b", r"\bдобавь\b", r"\bплиз\b", r"\bпожалуйста\b",
    r"\bв заметки\b", r"\bв базу\b", r"\bзафиксируй\b"
]


def clean_raw_text(text: str) -> str:
    cleaned = text.strip()
    for pattern in COMMAND_WORDS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^[,\.\-:;]+\s*", "", cleaned)
    cleaned = re.sub(r"\s*[,\.\-:;]+$", "", cleaned)
    return cleaned if cleaned else text.strip()


def extract_explicit_tags(text: str) -> List[str]:
    matches = re.findall(r"#([a-zA-Zа-яА-ЯёЁ0-9_]+(?:-[a-zA-Zа-яА-ЯёЁ0-9_]+)*)", text)
    tags = []
    seen = set()
    for t in matches:
        clean_t = t.lower()
        if clean_t not in seen:
            seen.add(clean_t)
            tags.append(t)
    return tags


def determine_fallback_section(text: str, tags: Optional[List[str]] = None) -> str:
    """Keyword & tag based heuristic classifier for section assignment."""
    lower = (text or "").lower()
    tag_str = " ".join(tags or []).lower()
    combined = f"{lower} {tag_str}"

    if any(w in combined for w in ["игра", "игр", "forza", "steam", "playstation", "xbox", "гейм", "гейминг", "геймер", "прохождение"]):
        return "games"
    if any(w in combined for w in ["фильм", "кино", "человек паук", "человек-паук", "марвел", "сериал", "премьера", "кинотеатр", "сеанс", "смотреть"]):
        return "movies"
    if any(w in combined for w in ["работ", "мфц", "документ", "паспорт", "госуслуг", "встреч", "клиент", "проект", "бизнес", "дедлайн", "офис", "договор"]):
        return "work"
    if any(w in combined for w in ["код", "программирован", "питон", "python", "js", "javascript", "бот", "сайт", "баг", "фича", "сервер", "разработк", "ai", "нейросет"]):
        return "tech"
    return "tasks"


def local_fallback_enhance(raw_text: str) -> Dict[str, Any]:
    """Reliable local NLP engine that works without any external API."""
    clean_body = clean_raw_text(raw_text)
    explicit_tags = extract_explicit_tags(raw_text)
    lower = clean_body.lower()
    inferred_tags = []
    category = "general"

    if any(w in lower for w in ["игра", "игр", "forza", "steam", "playstation", "xbox", "гейм", "гейминг", "геймер", "прохождение"]):
        category = "games"
        inferred_tags.extend(["игры", "развлечения", "планы"])
        if "forza" in lower:
            inferred_tags.insert(0, "forza")
    elif any(w in lower for w in ["фильм", "кино", "человек паук", "человек-паук", "марвел", "сериал", "премьера", "кинотеатр", "актёр", "актер", "режиссер", "смотреть", "мультфильм", "аниме", "сеанс"]):
        category = "cinema"
        inferred_tags.extend(["кино", "фильмы", "развлечения", "планы"])
        if "человек паук" in lower or "человек-паук" in lower:
            inferred_tags.insert(0, "человек-паук")
    elif any(w in lower for w in ["книга", "книг", "прочитать", "читать", "автор", "литература", "роман", "библиотека"]):
        category = "books"
        inferred_tags.extend(["книги", "чтение", "саморазвитие", "литература"])
    elif any(w in lower for w in ["купить", "заказать", "покупк", "озон", "вайлдберриз", "wb", "ozon", "кроссовки", "вещь", "магазин", "цена"]):
        category = "shopping"
        inferred_tags.extend(["покупки", "wishlist", "планы"])
    elif any(w in lower for w in ["код", "программирован", "питон", "python", "js", "javascript", "бот", "сайт", "баг", "фича", "сервер", "разработк"]):
        category = "tech"
        inferred_tags.extend(["it", "разработка", "технологии", "код"])
    elif any(w in lower for w in ["спорт", "зал", "тренировк", "бег", "питани", "диета", "здоровь", "врач"]):
        category = "sport"
        inferred_tags.extend(["спорт", "здоровье", "привычки"])
    elif any(w in lower for w in ["поездк", "поехать", "билет", "отель", "море", "отпуск", "самолет", "поезд", "город", "путешеств"]):
        category = "travel"
        inferred_tags.extend(["путешествия", "поездки", "отдых"])
    elif any(w in lower for w in ["проект", "работ", "клиент", "встреч", "дедлайн", "задач", "отчет"]):
        category = "work"
        inferred_tags.extend(["проекты", "работа", "задачи"])
    elif any(w in lower for w in ["деньги", "бюджет", "инвестиц", "зарплат", "расход", "доход"]):
        category = "finance"
        inferred_tags.extend(["финансы", "бюджет", "деньги"])
    elif any(w in lower for w in ["мысль", "идея", "инсайт", "подумал", "придумал", "вывод"]):
        category = "ideas"
        inferred_tags.extend(["мысли", "идеи", "инсайты"])
    else:
        inferred_tags.extend(["планы", "заметки"])

    combined_tags = []

    capitalized = clean_body[0].upper() + clean_body[1:] if clean_body else clean_body

    category_to_section = {
        "games": "games",
        "cinema": "movies",
        "work": "work",
        "tech": "tech",
        "shopping": "tasks",
        "books": "tasks",
        "sport": "tasks",
        "travel": "tasks",
        "finance": "work",
        "ideas": "tasks",
        "general": "tasks"
    }
    section = category_to_section.get(category, "tasks")
    section_label = SECTION_LABELS.get(section, "Заметки")

    if category == "games":
        enhanced_text = (
            f"Игровой план: {capitalized}\n\n"
            f"План игровой сессии и прохождения.\n\n"
            f"• Запустить игру и проверить актуальные обновления\n"
            f"• Выполнить текущие сюжетные задачи и сезонные задания\n"
            f"• Сохранить прогресс и ключевые достижения"
        )
        friendly_reply = "Сохранено."
    elif category == "cinema":
        movie_title = "«Человек-паук»" if ("человек паук" in lower or "человек-паук" in lower) else "в кино"
        enhanced_text = (
            f"Поход в кино: {movie_title}\n\n"
            f"Организация просмотра в кинотеатре.\n\n"
            f"• Проверить расписание сеансов и выбрать удобное время\n"
            f"• Забронировать лучшие места в зале\n"
            f"• Спланировать время до начала сеанса"
        )
        friendly_reply = "Сохранено."
    elif category == "shopping":
        enhanced_text = (
            f"Покупки / Wishlist: {capitalized}\n\n"
            f"План покупки и поиск оптимального предложения.\n\n"
            f"• Сравнить цены и отзывы на маркетплейсах\n"
            f"• Проверить характеристики, условия и сроки доставки\n"
            f"• Оформить заказ с максимальной выгодой"
        )
        friendly_reply = "Сохранено."
    elif category == "books":
        enhanced_text = (
            f"Книги и чтение: {capitalized}\n\n"
            f"План изучения материала и чтения литературы.\n\n"
            f"• Найти и приобрести книгу в удобном формате\n"
            f"• Выделить время для регулярного ежедневного чтения\n"
            f"• Фиксировать ключевые мысли, инсайты и выводы"
        )
        friendly_reply = "Сохранено."
    elif category == "work":
        enhanced_text = (
            f"Рабочая задача: {capitalized}\n\n"
            f"План реализации и критерии успешного выполнения.\n\n"
            f"• Детализировать этапы и определить контрольные точки\n"
            f"• Подготовить необходимые материалы и ресурсы для реализации\n"
            f"• Провести финальную проверку результатов перед сдачей"
        )
        friendly_reply = "Сохранено."
    elif category == "tech":
        enhanced_text = (
            f"Разработка и IT: {capitalized}\n\n"
            f"Техническая реализация задачи и обеспечение стабильности.\n\n"
            f"• Спроектировать архитектуру и логику работы компонентов\n"
            f"• Реализовать функционал и проверить критические сценарии\n"
            f"• Провести ревью и развернуть изменения"
        )
        friendly_reply = "Сохранено."
    else:
        enhanced_text = (
            f"{capitalized}\n\n"
            f"План выполнения и ключевые шаги.\n\n"
            f"• Определить приоритет и временные рамки выполнения\n"
            f"• Выполнить основные действия по поставленной задаче\n"
            f"• Зафиксировать финальный результат"
        )
        friendly_reply = "Сохранено."

    return {
        "enhanced_text": enhanced_text,
        "tags": [],
        "section": section,
        "friendly_reply": friendly_reply,
        "provider": "local_nlp"
    }


async def call_groq_api(raw_text: str, api_key: str, model: str = "llama-3.3-70b-versatile", system_prompt: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Call free ultra-fast Groq API."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    sys_prompt = system_prompt or SYSTEM_PROMPT
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Вот текст пользователя: {raw_text}"}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.5
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                parsed["provider"] = f"groq:{model}"
                return parsed
            else:
                err_text = await resp.text()
                logger.warning(f"Groq API error {resp.status}: {err_text}")
                return None


async def call_gemini_api(raw_text: str, api_key: str, model: str = "gemini-1.5-flash", system_prompt: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Call free Google Gemini API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    sys_prompt = system_prompt or SYSTEM_PROMPT
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{sys_prompt}\n\nПользователь прислал:\n{raw_text}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.5,
            "responseMimeType": "application/json"
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                text_part = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_part)
                parsed["provider"] = f"gemini:{model}"
                return parsed
            else:
                err_text = await resp.text()
                logger.warning(f"Gemini API error {resp.status}: {err_text}")
                return None


async def call_openrouter_api(raw_text: str, api_key: str, model: str = "meta-llama/llama-3.3-70b-instruct:free", system_prompt: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Call OpenRouter free models."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8080",
        "X-Title": "Notes Telegram Bot"
    }
    sys_prompt = system_prompt or SYSTEM_PROMPT
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Вот текст пользователя: {raw_text}"}
        ],
        "temperature": 0.5
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                clean_json = re.sub(r"^```(?:json)?\s*", "", content.strip())
                clean_json = re.sub(r"\s*```$", "", clean_json)
                parsed = json.loads(clean_json)
                parsed["provider"] = f"openrouter:{model}"
                return parsed
            else:
                err_text = await resp.text()
                logger.warning(f"OpenRouter API error {resp.status}: {err_text}")
                return None


async def enhance_note_async(raw_text: str) -> Dict[str, Any]:
    """
    Main async entrypoint for AI note enhancement.
    Checks for configured AI API keys, calls LLM, and gracefully falls back to local engine.
    """
    api_key = settings.AI_API_KEY.strip()
    provider = settings.AI_PROVIDER.lower().strip()
    model = settings.AI_MODEL.strip()

    if api_key:
        try:
            result = None
            if provider == "groq":
                result = await call_groq_api(raw_text, api_key, model or "llama-3.3-70b-versatile")
            elif provider in ["gemini", "google"]:
                result = await call_gemini_api(raw_text, api_key, model or "gemini-1.5-flash")
            elif provider == "openrouter":
                result = await call_openrouter_api(raw_text, api_key, model or "meta-llama/llama-3.3-70b-instruct:free")

            if result and isinstance(result, dict) and "enhanced_text" in result:
                # Merge any explicit #tags user might have typed
                explicit_tags = extract_explicit_tags(raw_text)
                combined = []
                seen = set()
                for t in explicit_tags + (result.get("tags") or []):
                    clean_t = str(t).replace("#", "").strip().lower()
                    if clean_t and clean_t not in seen:
                        seen.add(clean_t)
                        combined.append(str(t).replace("#", "").strip())
                result["tags"] = combined

                # Validate and normalize AI section
                sec = str(result.get("section", "")).lower().strip()
                if sec not in VALID_SECTIONS:
                    sec = determine_fallback_section(raw_text, result.get("tags") or [])
                result["section"] = sec
                return result
        except Exception as e:
            logger.warning(f"LLM enhancement failed, using local NLP: {e}")

    # Fallback to local NLP engine
    return local_fallback_enhance(raw_text)


def local_fallback_process(
    raw_text: str,
    existing_notes: List[Any],
    replied_note: Optional[Any] = None,
    force_question: bool = False
) -> Dict[str, Any]:
    """Rule-based question vs note creator when offline/fallback."""
    text_lower = raw_text.lower().strip()
    is_question = (
        force_question or
        "?" in raw_text or
        replied_note is not None or
        any(w in text_lower.split() for w in ["что", "как", "где", "когда", "какой", "какая", "какие", "сколько", "напомни", "найди", "покажи", "есть", "расскажи"]) or
        text_lower.startswith(("что ", "как ", "где ", "когда ", "какой ", "какая ", "какие ", "сколько ", "напомни ", "найди ", "покажи "))
    )

    if is_question:
        if replied_note:
            r_id = getattr(replied_note, "id", "?")
            r_text = getattr(replied_note, "text", "")
            return {
                "intent": "answer_question",
                "answer": f"В заметке №{r_id}:\n\n{r_text}",
                "related_note_id": r_id
            }

        search_tokens = [w for w in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", text_lower) if len(w) >= 3 and w not in ["что", "как", "где", "когда", "какой", "какая", "какие", "сколько", "напомни", "найди", "покажи", "заметк", "заметке", "заметки", "заметок"]]

        matches = []
        for n in existing_notes:
            n_text = (getattr(n, "text", "") or "").lower()
            score = sum(1 for token in search_tokens if token in n_text)
            if score > 0:
                matches.append((score, n))

        if matches:
            matches.sort(key=lambda x: x[0], reverse=True)
            best_note = matches[0][1]
            b_id = getattr(best_note, "id", "?")
            b_text = getattr(best_note, "text", "")
            return {
                "intent": "answer_question",
                "answer": f"В заметке указано:\n\n{b_text}",
                "related_note_id": b_id
            }
        else:
            return {
                "intent": "answer_question",
                "answer": "В ваших сохранённых заметках не найдено информации по этому вопросу.",
                "related_note_id": None
            }

    res = local_fallback_enhance(raw_text)
    res["intent"] = "create_note"
    return res


async def process_user_message_async(
    raw_text: str,
    existing_notes: List[Any],
    replied_note: Optional[Any] = None,
    force_question: bool = False
) -> Dict[str, Any]:
    """
    Intelligent message processor that detects whether user wants to:
    1. Ask a question about existing notes (search/consult/chat) -> "intent": "answer_question"
    2. Create a new note -> "intent": "create_note"
    """
    clean_text = raw_text.strip()
    if not clean_text:
        return {"intent": "answer_question", "answer": "Пожалуйста, напишите вопрос или заметку."}

    notes_context_lines = []
    for n in existing_notes[:40]:
        n_id = getattr(n, "id", "?")
        n_sec = getattr(n, "section", "tasks")
        n_sec_label = SECTION_LABELS.get(n_sec, n_sec)
        n_text = getattr(n, "text", "")
        notes_context_lines.append(f"• Заметка №{n_id} [Раздел: {n_sec_label}]:\n{n_text}")

    context_str = "\n\n".join(notes_context_lines) if notes_context_lines else "(Сохранённых заметок пока нет)"

    replied_context = ""
    if replied_note:
        r_id = getattr(replied_note, "id", "?")
        r_sec = getattr(replied_note, "section", "tasks")
        r_sec_label = SECTION_LABELS.get(r_sec, r_sec)
        r_text = getattr(replied_note, "text", "")
        replied_context = f"ПОЛЬЗОВАТЕЛЬ ОТВЕЧАЕТ НА КОНКРЕТНУЮ ЗАМЕТКУ №{r_id} (Раздел: {r_sec_label}):\n{r_text}\n"

    force_instruction = ""
    if force_question:
        force_instruction = "\nВАЖНО: Пользователь явно задал вопрос. СТРОГО выбери intent = 'answer_question'."

    sys_prompt = f"""Ты — персональный умный AI-ассистент в FastNotes с доступом к личным заметкам пользователя.

БАЗА СУЩЕСТВУЮЩИХ ЗАМЕТОК:
{context_str}

{replied_context}
{force_instruction}

ТВОЯ ЗАДАЧА:
Определи намерение пользователя (intent):

1. "answer_question":
Если пользователь:
- Задаёт вопрос («что у меня по...», «какая цель...», «что мне сделать...», «какие задачи...», «что купить...», «сколько заметок...»)
- Просит напомнить или найти информацию («напомни...», «найди...», «покажи...», «где записано...», «что там про...»)
- Отвечает на существующую заметку или спрашивает о ней
- Консультируется по содержанию своих заметок
- Принудительно задал вопрос через команду /ask
ПРАВИЛА ДЛЯ "answer_question":
- Отвечай естественно, прямо и по делу на русском языке, как персональный ассистент.
- НЕ нужно называть технические номера заметок («№3», «№1»), если пользователь сам явно не спросил номер. Говори по-человечески: называй тему/заголовок заметки (например: «В заметке по проекту указано...») или отвечай сразу на вопрос: «Цель проекта — набрать максимальный балл (100 баллов).»
- Если информации нет в базе заметок, вежливо скажи: «В ваших сохранённых заметках нет информации по этому вопросу.»
- БЕЗ лишних формальностей, приветствий и шаблонных фраз. Сразу ответ по сути.

2. "create_note":
Если пользователь прислал новую мысль, план, задачу, идею или список, который нужно сохранить в базу как новую заметку.
ПРАВИЛА ДЛЯ "create_note":
- Сформируй качественную структурированную заметку в премиальном стиле Apple:
  - Чёткий заголовок
  - Краткий контекст (1–2 предложения)
  - 3–4 конкретных практических шага/пункта с маркером «•»
  - СТРОГО БЕЗ ЭМОДЗИ
  - Раздел (games, movies, work, tasks, tech)

ФОРМАТ ОТВЕТА (СТРОГО ВАЛИДНЫЙ JSON):
Для answer_question:
{{
  "intent": "answer_question",
  "answer": "Точный текст ответа с деталями из заметок",
  "related_note_id": 3
}}

Для create_note:
{{
  "intent": "create_note",
  "enhanced_text": "Заголовок\\n\\nОписание...\\n\\n• Пункт 1\\n• Пункт 2\\n• Пункт 3",
  "tags": [],
  "section": "games" | "movies" | "work" | "tasks" | "tech",
  "friendly_reply": "Сохранено."
}}
Никакого другого текста вокруг JSON!"""

    api_key = settings.AI_API_KEY.strip()
    provider = settings.AI_PROVIDER.lower().strip()
    model = settings.AI_MODEL.strip()

    if api_key:
        try:
            res = None
            if provider == "groq":
                res = await call_groq_api(clean_text, api_key, model or "llama-3.3-70b-versatile", system_prompt=sys_prompt)
            elif provider in ["gemini", "google"]:
                res = await call_gemini_api(clean_text, api_key, model or "gemini-1.5-flash", system_prompt=sys_prompt)
            elif provider == "openrouter":
                res = await call_openrouter_api(clean_text, api_key, model or "meta-llama/llama-3.3-70b-instruct:free", system_prompt=sys_prompt)

            if res and isinstance(res, dict) and "intent" in res:
                if res["intent"] == "answer_question":
                    return res
                elif res["intent"] == "create_note" and "enhanced_text" in res:
                    sec = str(res.get("section", "")).lower().strip()
                    if sec not in VALID_SECTIONS:
                        sec = determine_fallback_section(clean_text, res.get("tags") or [])
                    res["section"] = sec
                    return res
        except Exception as e:
            logger.warning(f"AI message processing failed, falling back to local engine: {e}")

    return local_fallback_process(clean_text, existing_notes, replied_note=replied_note, force_question=force_question)



async def classify_section_async(text: str) -> str:
    """
    Dedicated AI method to classify any text or note into one of standard sections:
    'games', 'movies', 'work', 'tasks', 'tech'
    """
    clean = text.strip()
    if not clean:
        return "tasks"

    api_key = settings.AI_API_KEY.strip()
    provider = settings.AI_PROVIDER.lower().strip()
    model = settings.AI_MODEL.strip()

    if api_key:
        try:
            sys_prompt = """Ты — точный классификатор заметок. Выбери ровно один раздел:
- games (Игры: видеоигры, консоли, Steam, Forza, гейминг)
- movies (Фильмы: кино, фильмы, сериалы, сеансы, кинотеатры, Человек-паук)
- work (Работа: работа, клиенты, проекты, договоры, документы, МФЦ, госуслуги, встречи, дедлайны)
- tasks (Задачи и быт: быт, стирка, уборка, покупки, дом, личные дела)
- tech (Технологии: программирование, IT, код, боты, Python, AI, сайты, серверы)

Ответь СТРОГО валидным JSON: {"section": "games" | "movies" | "work" | "tasks" | "tech"}"""

            if provider == "groq":
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": model or "qwen/qwen3.8-27b",
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": clean}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"]
                            parsed = json.loads(content)
                            sec = str(parsed.get("section", "")).lower().strip()
                            if sec in VALID_SECTIONS:
                                return sec
        except Exception as e:
            logger.warning(f"AI classification failed, using fallback: {e}")

    return determine_fallback_section(text)


def enhance_note(raw_text: str) -> Dict[str, Any]:
    """Synchronous wrapper for local fallback."""
    return local_fallback_enhance(raw_text)
