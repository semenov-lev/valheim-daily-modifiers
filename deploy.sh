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

if [ ! -d "$SERVER_DIR" ]; then
    echo "ОШИБКА: $SERVER_DIR не найден" >&2
    exit 1
fi

echo "=== Деплой в $SERVER_DIR ==="

install -o "$STEAM_USER" -g "$STEAM_GROUP" -m 644 "$REPO_DIR/modifiers.json"  "$SERVER_DIR/modifiers.json"
install -o "$STEAM_USER" -g "$STEAM_GROUP" -m 755 "$REPO_DIR/start_valheim.sh" "$SERVER_DIR/start_valheim.sh"
install -o "$STEAM_USER" -g "$STEAM_GROUP" -m 755 "$REPO_DIR/send_tg.py"       "$SERVER_DIR/send_tg.py"

if [ ! -f "$SERVER_DIR/tg.env" ]; then
    install -o "$STEAM_USER" -g "$STEAM_GROUP" -m 600 "$REPO_DIR/tg.env.example" "$SERVER_DIR/tg.env"
    echo "ВНИМАНИЕ: создан $SERVER_DIR/tg.env — заполните токен и chat_id"
fi

echo "=== Установка systemd-юнитов ==="
install -m 644 "$REPO_DIR/systemd/valheim.service"        /etc/systemd/system/
install -m 644 "$REPO_DIR/systemd/valheim-rotate.service" /etc/systemd/system/
install -m 644 "$REPO_DIR/systemd/valheim-rotate.timer"   /etc/systemd/system/
systemctl daemon-reload

echo
echo "=== Готово ==="
echo "Проверьте диффы перед перезапуском: systemctl cat valheim.service"
echo "Активировать таймер:    systemctl enable --now valheim-rotate.timer"
echo "Применить модификаторы: systemctl restart valheim"
