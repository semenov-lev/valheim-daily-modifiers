#!/usr/bin/env python3
"""Отправка уведомления о новых модификаторах Valheim в Telegram через прокси."""
import json
import os
import sys

import requests

BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
CHAT_ID   = os.environ.get("TG_CHAT_ID")
PROXY_URL = os.environ.get("TG_PROXY_URL", "http://127.0.0.1:8080")
LAST      = "/home/steam/Valheim-Server/last_modifiers.json"

if not BOT_TOKEN or not CHAT_ID:
    print("ОШИБКА: TG_BOT_TOKEN или TG_CHAT_ID не заданы", file=sys.stderr)
    sys.exit(1)

if not os.path.exists(LAST):
    print(f"ОШИБКА: {LAST} не найден", file=sys.stderr)
    sys.exit(1)

with open(LAST, encoding="utf-8") as f:
    m = json.load(f)


def fmt(value, default="normal"):
    return value if value else default


setkeys = m.get("setkeys") or []
setkeys_line = ", ".join(setkeys) if setkeys else "нет"

text = (
    "🎮 <b>Valheim: новые модификаторы мира</b>\n\n"
    f"⚔️ combat: <b>{fmt(m.get('combat'))}</b>\n"
    f"💀 deathpenalty: <b>{fmt(m.get('deathpenalty'))}</b>\n"
    f"📦 resources: <b>{fmt(m.get('resources'))}</b>\n"
    f"👹 raids: <b>{fmt(m.get('raids'))}</b>\n"
    f"🌀 portals: <b>{fmt(m.get('portals'))}</b>\n"
    f"🔧 setkeys: <b>{setkeys_line}</b>\n\n"
    "<i>Сервер перезапущен, мир сохранён.</i>"
)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
proxies = {"http": PROXY_URL, "https": PROXY_URL}

try:
    r = requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
        proxies=proxies,
        timeout=30,
    )
    r.raise_for_status()
    print("Telegram OK")
except requests.RequestException as e:
    print(f"ОШИБКА отправки в Telegram: {e}", file=sys.stderr)
    sys.exit(2)
