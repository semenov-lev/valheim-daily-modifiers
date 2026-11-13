#!/bin/bash
set -euo pipefail

SERVER_DIR="/home/steam/Valheim-Server"
JSON="$SERVER_DIR/modifiers.json"
LAST="$SERVER_DIR/last_modifiers.json"
PICKER="$SERVER_DIR/modifier_picker.py"
ROTATE_FLAG="/run/valheim/rotate.flag"

command -v jq &>/dev/null || { echo "jq не установлен" >&2; exit 1; }
[ -f "$PICKER" ] || { echo "ОШИБКА: $PICKER не найден" >&2; exit 1; }
[ -f "$JSON" ] || { echo "ОШИБКА: $JSON не найден" >&2; exit 1; }
[ -x "$SERVER_DIR/start_server_configured.sh" ] || {
    echo "ОШИБКА: $SERVER_DIR/start_server_configured.sh не найден или не исполняем" >&2
    exit 1
}

# Решаем, генерировать новую комбинацию или применить сохранённую.
# Ротация (новый выбор) происходит ТОЛЬКО когда rotate.service создал
# маркер /run/valheim/rotate.flag. Любые другие старты (needrestart после
# обновления libc, ребут хоста, ручной restart, падение) применяют уже
# сохранённую комбинацию из last_modifiers.json — сложность не меняется.
# Маркер лежит в /run/valheim (каталог с владельцем steam), а не прямо в
# /run: удаление файла определяется правами на КАТАЛОГ, а /run принадлежит
# root — скрипт (User=steam) не смог бы удалить оттуда маркер.
ROTATE=0
if [ -f "$ROTATE_FLAG" ]; then
    ROTATE=1
    rm -f "$ROTATE_FLAG"
fi

if [ "$ROTATE" -eq 1 ] || [ ! -f "$LAST" ]; then
    # Новая комбинация: взвешенный выбор + балансировка difficulty score
    COMBO_JSON=$(python3 "$PICKER" "$JSON")

    # Атомарно пишем last_modifiers.json + timestamp
    TMP=$(mktemp)
    echo "$COMBO_JSON" | jq --arg ts "$(date -Iseconds)" '. + {timestamp: $ts}' > "$TMP"
    mv "$TMP" "$LAST"
    echo "Режим: РОТАЦИЯ (новая комбинация модификаторов)"
else
    # Применяем уже сохранённую комбинацию (без изменения сложности)
    COMBO_JSON=$(cat "$LAST")
    echo "Режим: ПРИМЕНЕНИЕ сохранённой комбинации (без ротации)"
fi

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
