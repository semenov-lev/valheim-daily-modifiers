#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="/home/steam/Valheim-Server"
STEAM_USER="steam"
STEAM_GROUP="steam"

if [ "$(id -u)" -ne 0 ]; then
    echo "ОШИБКА: deploy.sh нужно запускать от root (sudo ./deploy.sh)" >&2
    exit 1
fi

echo "=== Проверка зависимостей ==="

if ! command -v jq &>/dev/null; then
    echo "ОШИБКА: jq не установлен. apt install jq" >&2
    exit 1
fi

if ! python3 -c "import requests" 2>/dev/null; then
    echo "ОШИБКА: python3-requests не установлен. apt install python3-requests" >&2
    exit 1
fi

# PySocks нужен только если в tg.env используется SOCKS-прокси.
# На этапе деплоя tg.env может ещё не существовать — проверяем мягко.
if [ -f "$SERVER_DIR/tg.env" ] && grep -qE '^TG_PROXY_URL=socks' "$SERVER_DIR/tg.env"; then
    if ! python3 -c "import socks" 2>/dev/null; then
        echo "ОШИБКА: tg.env указывает SOCKS-прокси, но PySocks не установлен." >&2
        echo "        Установите: sudo apt install python3-socks" >&2
        exit 1
    fi
fi

if [ ! -d "$SERVER_DIR" ]; then
    echo "ОШИБКА: $SERVER_DIR не найден" >&2
    exit 1
fi

echo "=== Валидация modifiers.json ==="
if ! python3 -c "
import json, sys
sys.path.insert(0, '$REPO_DIR')
from modifier_picker import validate_config
with open('$REPO_DIR/modifiers.json') as f:
    problems = validate_config(json.load(f))
if problems:
    for k, v in problems.items():
        print(f'  [{k}] {v}', file=sys.stderr)
    sys.exit(1)
"; then
    echo "ОШИБКА: modifiers.json невалиден, деплой прерван" >&2
    exit 1
fi
echo "OK"

echo "=== Деплой в $SERVER_DIR ==="

install -o "$STEAM_USER" -g "$STEAM_GROUP" -m 644 "$REPO_DIR/modifiers.json"              "$SERVER_DIR/modifiers.json"
install -o "$STEAM_USER" -g "$STEAM_GROUP" -m 644 "$REPO_DIR/modifier_descriptions.json"  "$SERVER_DIR/modifier_descriptions.json"
install -o "$STEAM_USER" -g "$STEAM_GROUP" -m 755 "$REPO_DIR/start_valheim.sh"            "$SERVER_DIR/start_valheim.sh"
install -o "$STEAM_USER" -g "$STEAM_GROUP" -m 755 "$REPO_DIR/send_tg.py"                  "$SERVER_DIR/send_tg.py"
install -o "$STEAM_USER" -g "$STEAM_GROUP" -m 755 "$REPO_DIR/modifier_picker.py"          "$SERVER_DIR/modifier_picker.py"

if [ ! -f "$SERVER_DIR/tg.env" ]; then
    install -o "$STEAM_USER" -g "$STEAM_GROUP" -m 600 "$REPO_DIR/tg.env.example" "$SERVER_DIR/tg.env"
    echo "ВНИМАНИЕ: создан $SERVER_DIR/tg.env — заполните токен и chat_id"
fi

echo "=== Удаление старых юнитов (если есть) ==="
for old in valheim.service valheim-rotate.service valheim-rotate.timer; do
    if [ -f "/etc/systemd/system/$old" ]; then
        echo "  удаляю /etc/systemd/system/$old"
        systemctl disable --now "$old" 2>/dev/null || true
        rm -f "/etc/systemd/system/$old"
    fi
done
systemctl daemon-reload

echo "=== Установка systemd-сервисов ==="
install -m 644 "$REPO_DIR/systemd/valheim-server.service"        /etc/systemd/system/
install -m 644 "$REPO_DIR/systemd/valheim-server-rotate.service" /etc/systemd/system/

echo "=== Генерация таймера из шаблона ==="
"$REPO_DIR/apply-schedule.sh"

echo
echo "=== Готово ==="
echo "Проверить юнит:          systemctl cat valheim-server.service"
echo "Активировать таймер:     systemctl enable --now valheim-server-rotate.timer"
echo "Применить модификаторы:  systemctl restart valheim-server.service"
