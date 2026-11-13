#!/usr/bin/env python3
"""Отправка уведомления о новых модификаторах Valheim в Telegram через SOCKS5-прокси.

Дополнительно:
  • генерирует шутливый ИИ-комментарий к комбинации через OpenAI-совместимый
    API (DeepSeek / Open WebUI / OpenAI) — если задан OPENAI_API_KEY;
  • закрепляет новое сообщение и открепляет предыдущее (id хранится в
    telegram_state.json).
"""
import json
import os
import sys

import requests

BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
CHAT_ID = os.environ.get("TG_CHAT_ID")
PROXY_URL = os.environ.get("TG_PROXY_URL", "")

# OpenAI-совместимый API для генерации анализа (опционально).
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com").rstrip("/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "deepseek-chat")
try:
    OPENAI_ANALYSIS_MAX_CHARS = int(os.environ.get("OPENAI_ANALYSIS_MAX_CHARS", "320"))
except ValueError:
    OPENAI_ANALYSIS_MAX_CHARS = 320

SERVER_DIR = "/home/steam/Valheim-Server"
LAST = f"{SERVER_DIR}/last_modifiers.json"
DESC = f"{SERVER_DIR}/modifier_descriptions.json"
STATE = f"{SERVER_DIR}/telegram_state.json"

# --- Проверка переменных окружения ---
if not BOT_TOKEN or not CHAT_ID:
    print("ОШИБКА: TG_BOT_TOKEN или TG_CHAT_ID не заданы", file=sys.stderr)
    sys.exit(1)

if not PROXY_URL:
    print("ОШИБКА: TG_PROXY_URL не задан в tg.env", file=sys.stderr)
    sys.exit(1)

# SOCKS5-прокси требует PySocks.
if PROXY_URL.startswith(("socks5://", "socks5h://", "socks4://", "socks4a://")):
    try:
        import socks  # noqa: F401  (PySocks)
    except ImportError:
        print(
            "ОШИБКА: для SOCKS-прокси нужен PySocks.\n"
            "Установите: pip install 'requests[socks]'",
            file=sys.stderr,
        )
        sys.exit(1)

# --- Проверка файлов ---
if not os.path.exists(LAST):
    print(
        f"ОШИБКА: {LAST} не найден.\n"
        "Файл создаётся start_valheim.sh при каждом запуске сервера.\n"
        "Если сервер ещё ни разу не стартовал после деплоя — это ожидаемо.\n"
        "Проверьте: journalctl -u valheim-server.service -n 50",
        file=sys.stderr,
    )
    sys.exit(1)

if not os.path.exists(DESC):
    print(f"ОШИБКА: {DESC} не найден. Запустите deploy.sh повторно.", file=sys.stderr)
    sys.exit(1)

with open(LAST, encoding="utf-8") as f:
    active = json.load(f)

with open(DESC, encoding="utf-8") as f:
    desc = json.load(f)


def describe(modifier: str, value) -> str:
    """Возвращает строку для Telegram для одного модификатора.

    Новый формат last_modifiers.json пишет 'normal' явным значением (а не
    null), поэтому обычно value == 'normal'. Значение None возможно только
    для файла от старой версии — трактуем его как normal.
    """
    lookup_key = "normal" if value is None else value
    entry = desc.get(modifier, {}).get(lookup_key)

    if entry is None:
        return f"{lookup_key} (описание не найдено)"

    return f"{entry['label']} — {entry['description']}"


def build_modifiers_block() -> str:
    """Текстовый блок с активными модификаторами (без HTML-разметки).

    Используется и для тела сообщения, и как входные данные для модели,
    чтобы промпт опирался ровно на то, что видит игрок.
    """
    block = [
        f"Бой: {describe('combat', active.get('combat'))}",
        f"Штраф за смерть: {describe('deathpenalty', active.get('deathpenalty'))}",
        f"Ресурсы: {describe('resources', active.get('resources'))}",
        f"Рейды: {describe('raids', active.get('raids'))}",
        f"Порталы: {describe('portals', active.get('portals'))}",
    ]
    setkeys = active.get("setkeys") or []
    if setkeys:
        flags = []
        for key in setkeys:
            entry = desc.get("setkeys", {}).get(key)
            flags.append(f"{entry['label']} — {entry['description']}" if entry else key)
        block.append("Доп. флаги: " + "; ".join(flags))
    return "\n".join(block)


def truncate(text: str, max_chars: int) -> str:
    """Обрезает текст до max_chars по границе слова, добавляя многоточие."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Отрезаем по последнему пробелу, чтобы не рвать слово.
    sp = cut.rfind(" ")
    if sp > max_chars * 0.6:
        cut = cut[:sp]
    return cut.rstrip(" ,.;:—-") + "…"


def generate_analysis(modifiers_block: str):
    """Генерирует шутливый ИИ-комментарий через OpenAI-совместимый API.

    Возвращает текст или None (если ключ не задан / произошла ошибка —
    fail-soft, сообщение уйдёт без анализа).
    """
    if not OPENAI_API_KEY:
        return None

    system_prompt = (
        "Ты — остроумный игровой комментатор сервера Valheim. Твоя задача — "
        "коротко и с юмором прокомментировать новый набор мировых модификаторов, "
        "которые включились на сервере на сегодня. Ты хорошо знаешь Valheim: "
        "боссов, биомы, крафт, рейды, механику смерти и порталов.\n\n"
        "Пиши на русском, живо и по-доброму, мат и оскорбления — допускаются. "
        "Не выдумывай модификаторы, которых нет во входных данных. "
        "Не используй списки и заголовки — только связный абзац. "
        f"Объём — не более {OPENAI_ANALYSIS_MAX_CHARS} символов."
    )
    user_prompt = (
        "Сегодня на сервере обновились настройки сложности мира. Ниже — активные "
        "модификаторы (название и краткое описание каждого):\n\n"
        f"{modifiers_block}\n\n"
        "Кратко и с юмором опиши, каким будет этот игровой день: каково придётся "
        "викингам, что их ждёт, к чему готовиться. "
        f"Уложись в {OPENAI_ANALYSIS_MAX_CHARS} символов."
    )

    try:
        resp = requests.post(
            f"{OPENAI_BASE_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 220,
                "temperature": 0.9,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        # OpenAI-совместимые API могут вернуть None/пусто.
        if not content or not content.strip():
            return None
        return truncate(content, OPENAI_ANALYSIS_MAX_CHARS)
    except (requests.RequestException, KeyError, ValueError, IndexError) as e:
        print(f"ВНИМАНИЕ: не удалось сгенерировать ИИ-анализ: {e}", file=sys.stderr)
        return None


def load_state() -> dict:
    """Читает telegram_state.json; при ошибке возвращает пустой dict."""
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict) -> None:
    """Атомарно пишет telegram_state.json."""
    tmp = f"{STATE}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE)
    except OSError as e:
        print(f"ВНИМАНИЕ: не удалось сохранить {STATE}: {e}", file=sys.stderr)


# --- Сборка сообщения ---
modifiers_block = build_modifiers_block()

lines = [
    "🎮 <b>Valheim: новые модификаторы мира</b>",
    "",
    f"⚔️ <b>Бой:</b> {describe('combat', active.get('combat'))}",
    f"💀 <b>Штраф за смерть:</b> {describe('deathpenalty', active.get('deathpenalty'))}",
    f"📦 <b>Ресурсы:</b> {describe('resources', active.get('resources'))}",
    f"👹 <b>Рейды:</b> {describe('raids', active.get('raids'))}",
    f"🌀 <b>Порталы:</b> {describe('portals', active.get('portals'))}",
]

setkeys = active.get("setkeys") or []
if setkeys:
    lines.append("")
    lines.append("🔧 <b>Дополнительные флаги:</b>")
    for key in setkeys:
        entry = desc.get("setkeys", {}).get(key)
        if entry:
            lines.append(f"• <b>{entry['label']}</b> — {entry['description']}")
        else:
            lines.append(f"• {key}")

lines.append("")

# ИИ-анализ (если настроен) — отдельным абзацем внизу.
analysis = generate_analysis(modifiers_block)
if analysis:
    lines.append("")
    lines.append(analysis)

text = "\n".join(lines)

api_base = f"https://api.telegram.org/bot{BOT_TOKEN}"
proxies = {"http": PROXY_URL, "https": PROXY_URL}

# --- Шаг 1: отправка сообщения ---
try:
    r = requests.post(
        f"{api_base}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
        proxies=proxies,
        timeout=30,
    )
    r.raise_for_status()
except requests.RequestException as e:
    print(f"ОШИБКА отправки в Telegram: {e}", file=sys.stderr)
    sys.exit(2)

try:
    message_id = r.json()["result"]["message_id"]
except (KeyError, ValueError) as e:
    # Сообщение ушло (HTTP 200), но структура ответа неожиданная.
    # Это не повод падать: уведомление доставлено, пин просто не сделаем.
    print(f"ВНИМАНИЕ: не удалось извлечь message_id из ответа: {e}", file=sys.stderr)
    print("Telegram OK (not pinned)")
    sys.exit(0)

# --- Шаг 2: закрепление нового сообщения (не критично) ---
state = load_state()
prev_pinned_id = state.get("pinned_message_id")

pinned = False
try:
    pin = requests.post(
        f"{api_base}/pinChatMessage",
        json={
            "chat_id": CHAT_ID,
            "message_id": message_id,
            "disable_notification": True,
        },
        proxies=proxies,
        timeout=30,
    )
    pin.raise_for_status()
    pinned = True
    print("Telegram OK (pinned)")
except requests.RequestException as e:
    # Сообщение уже доставлено — это главное. Пин мог не сработать по
    # множеству причин: бот не админ, нет права can_pin_messages,
    # лимит закреплений, сетевой сбой. Это не повод валить весь скрипт.
    print(f"ВНИМАНИЕ: сообщение отправлено, но закрепить не удалось: {e}", file=sys.stderr)

# --- Шаг 3: открепление предыдущего сообщения (только WARNING при сбое) ---
if pinned and prev_pinned_id and prev_pinned_id != message_id:
    try:
        unpin = requests.post(
            f"{api_base}/unpinChatMessage",
            json={"chat_id": CHAT_ID, "message_id": prev_pinned_id},
            proxies=proxies,
            timeout=30,
        )
        unpin.raise_for_status()
        print(f"Telegram OK (unpinned previous {prev_pinned_id})")
    except requests.RequestException as e:
        # Сообщение могло быть удалено вручную — это не критично.
        print(
            f"ВНИМАНИЕ: не удалось открепить предыдущее сообщение "
            f"{prev_pinned_id}: {e}",
            file=sys.stderr,
        )

# --- Шаг 4: сохраняем актуальный id закрепления ---
if pinned:
    save_state({"pinned_message_id": message_id})

if not pinned:
    print("Telegram OK (not pinned)")
