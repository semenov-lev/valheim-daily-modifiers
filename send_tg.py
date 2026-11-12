#!/usr/bin/env python3
"""Отправка уведомления о новых модификаторах Valheim в Telegram через SOCKS5-прокси."""
import json
import os
import sys

import requests

BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
CHAT_ID = os.environ.get("TG_CHAT_ID")
PROXY_URL = os.environ.get("TG_PROXY_URL", "")
LAST = "/home/steam/Valheim-Server/last_modifiers.json"
DESC = "/home/steam/Valheim-Server/modifier_descriptions.json"

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
lines.append("<i>Сервер запущен, мир сохранён.</i>")

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

# --- Шаг 2: закрепление (не критично) ---
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
    print("Telegram OK (pinned)")
except requests.RequestException as e:
    # Сообщение уже доставлено — это главное. Пин мог не сработать по
    # множеству причин: бот не админ, нет права can_pin_messages,
    # лимит закреплений, сетевой сбой. Это не повод валить весь скрипт.
    print(f"ВНИМАНИЕ: сообщение отправлено, но закрепить не удалось: {e}", file=sys.stderr)
    print("Telegram OK (not pinned)")
    sys.exit(0)
