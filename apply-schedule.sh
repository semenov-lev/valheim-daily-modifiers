#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="/home/steam/Valheim-Server"
JSON="$SERVER_DIR/modifiers.json"
TEMPLATE="$REPO_DIR/systemd/valheim-server-rotate.timer.template"
TARGET="/etc/systemd/system/valheim-server-rotate.timer"

if [ "$(id -u)" -ne 0 ]; then
    echo "ОШИБКА: apply-schedule.sh нужно запускать от root (sudo ./apply-schedule.sh)" >&2
    exit 1
fi

[ -f "$JSON" ] || { echo "ОШИБКА: $JSON не найден" >&2; exit 1; }
[ -f "$TEMPLATE" ] || { echo "ОШИБКА: $TEMPLATE не найден" >&2; exit 1; }

RESTART_TIME=$(jq -r '.schedule.restart_time // "05:00"' "$JSON")

# Валидация формата HH:MM — иначе systemd молча не распарсит OnCalendar
if ! [[ "$RESTART_TIME" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
    echo "ОШИБКА: некорректный restart_time '$RESTART_TIME' в $JSON (ожидается HH:MM)" >&2
    exit 1
fi

echo "Применяю расписание: ежедневно в $RESTART_TIME"
sed "s/__RESTART_TIME__/$RESTART_TIME/" "$TEMPLATE" > "$TARGET"
chmod 644 "$TARGET"
systemctl daemon-reload

if systemctl is-enabled --quiet valheim-server-rotate.timer 2>/dev/null; then
    systemctl restart valheim-server-rotate.timer
    echo "Таймер перезапущен."
else
    echo "Таймер ещё не активирован. Включите: systemctl enable --now valheim-server-rotate.timer"
fi

systemctl list-timers valheim-server-rotate.timer --no-pager
