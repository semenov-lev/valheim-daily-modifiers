#!/bin/bash
set -euo pipefail

SERVER_DIR="/home/steam/Valheim-Server"
JSON="$SERVER_DIR/modifiers.json"
LAST="$SERVER_DIR/last_modifiers.json"
PICKER="$SERVER_DIR/modifier_picker.py"

command -v jq &>/dev/null || { echo "jq не установлен" >&2; exit 1; }
[ -f "$PICKER" ] || { echo "ОШИБКА: $PICKER не найден" >&2; exit 1; }
[ -f "$JSON" ] || { echo "ОШИБКА: $JSON не найден" >&2; exit 1; }
[ -x "$SERVER_DIR/start_server_configured.sh" ] || {
    echo "ОШИБКА: $SERVER_DIR/start_server_configured.sh не найден или не исполняем" >&2
    exit 1
}

# Python выбирает комбинацию (JSON в stdout)
COMBO_JSON=$(python3 "$PICKER" "$JSON")

# Атомарно пишем last_modifiers.json + timestamp
TMP=$(mktemp)
echo "$COMBO_JSON" | jq --arg ts "$(date -Iseconds)" '. + {timestamp: $ts}' > "$TMP"
mv "$TMP" "$LAST"

# Собираем -modifier для всего, кроме normal
ARGS=()
while IFS= read -r line; do
    ARGS+=("$line")
done < <(echo "$COMBO_JSON" | jq -r '
    to_entries[]
    | select(.key | startswith("_") | not)
    | select(.key != "setkeys")
    | select(.value != "normal" and .value != null)
    | "-modifier", .key, .value
')

# setkeys (фиксированный массив из JSON)
while IFS= read -r key; do
    [ -n "$key" ] && ARGS+=(-setkey "$key")
done < <(jq -r '.setkeys[]?' "$JSON")

# Лог
echo "=== Valheim start: $(date -Iseconds) ==="
echo "$COMBO_JSON" | jq -c '{combat, deathpenalty, resources, raids, portals, _difficulty_score, _attempts}'
echo "==========================================="

# Предупреждение, если start_server_configured.sh не пробрасывает "$@":
# без этого модификаторы молча не дойдут до процесса сервера.
if ! grep -q '\$@\|\$\*' "$SERVER_DIR/start_server_configured.sh" 2>/dev/null; then
    echo "ВНИМАНИЕ: start_server_configured.sh, возможно, не пробрасывает \"\$@\"" >&2
    echo "         Добавьте \"\$@\" в строку запуска valheim_server.x86_64." >&2
fi

cd "$SERVER_DIR"
exec ./start_server_configured.sh -preset normal "${ARGS[@]}"
