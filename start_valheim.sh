#!/bin/bash
set -euo pipefail

SERVER_DIR="/home/steam/Valheim-Server"
JSON="$SERVER_DIR/modifiers.json"
LAST="$SERVER_DIR/last_modifiers.json"

# --- Проверки ---
command -v jq &>/dev/null || { echo "ОШИБКА: jq не установлен. apt install jq" >&2; exit 1; }
[ -f "$JSON" ] || { echo "ОШИБКА: $JSON не найден" >&2; exit 1; }
[ -x "$SERVER_DIR/start_server_configured.sh" ] || {
    echo "ОШИБКА: $SERVER_DIR/start_server_configured.sh не найден или не исполняем" >&2
    exit 1
}

# --- Выбор случайных значений ---
pick() { jq -r ".pool.$1[]" "$JSON" | shuf -n1; }

COMBAT=$(pick combat)
DEATH=$(pick deathpenalty)
RESOURCES=$(pick resources)
RAIDS=$(pick raids)
PORTALS=$(pick portals)

# --- Сборка аргументов ---
ARGS=()
add_mod() {
    local key="$1" val="$2"
    if [ -n "$val" ]; then
        ARGS+=(-modifier "$key" "$val")
    fi
}

add_mod combat       "$COMBAT"
add_mod deathpenalty "$DEATH"
add_mod resources    "$RESOURCES"
add_mod raids        "$RAIDS"
add_mod portals      "$PORTALS"

# setkeys (фиксированный массив из JSON)
SETKEYS_ARRAY=$(jq -c '.setkeys // []' "$JSON")
while IFS= read -r key; do
    if [ -n "$key" ]; then
        ARGS+=(-setkey "$key")
    fi
done < <(jq -r '.setkeys[]?' "$JSON")

# --- Атомарная запись last_modifiers.json для send_tg.py ---
TMP=$(mktemp)
jq -n \
    --arg timestamp "$(date -Iseconds)" \
    --arg combat "$COMBAT" \
    --arg deathpenalty "$DEATH" \
    --arg resources "$RESOURCES" \
    --arg raids "$RAIDS" \
    --arg portals "$PORTALS" \
    --argjson setkeys "$SETKEYS_ARRAY" \
    '{timestamp:$timestamp,
      combat:(if $combat=="" then null else $combat end),
      deathpenalty:(if $deathpenalty=="" then null else $deathpenalty end),
      resources:(if $resources=="" then null else $resources end),
      raids:(if $raids=="" then null else $raids end),
      portals:(if $portals=="" then null else $portals end),
      setkeys:$setkeys}' > "$TMP"
mv "$TMP" "$LAST"

# --- Лог ---
echo "=== Valheim start: $(date -Iseconds) ==="
echo "combat=${COMBAT:-normal}  deathpenalty=${DEATH:-normal}  resources=${RESOURCES:-normal}"
echo "raids=${RAIDS:-normal}  portals=${PORTALS:-normal}"
echo "setkeys=$(jq -r '.setkeys | join(",")' "$JSON" 2>/dev/null || echo "none")"
echo "==========================================="

# --- Предупреждение, если start_server_configured.sh не пробрасывает "$@" ---
if ! grep -q '\$@\|\$*' "$SERVER_DIR/start_server_configured.sh" 2>/dev/null; then
    echo "ВНИМАНИЕ: start_server_configured.sh, возможно, не пробрасывает \"\$@\"" >&2
    echo "         Добавьте \"\$@\" в строку запуска valheim_server.x86_64." >&2
fi

# --- Запуск: exec заменяет bash на процесс сервера ---
cd "$SERVER_DIR"
exec ./start_server_configured.sh "${ARGS[@]}"
