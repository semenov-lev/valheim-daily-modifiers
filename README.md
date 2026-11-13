# valheim-daily-modifiers

Набор скриптов и systemd-юнитов для выделенного сервера Valheim (Ubuntu 24.04):

- 🎲 **Ежедневная случайная ротация world modifiers** — комбинация `combat`,
  `deathpenalty`, `resources`, `raids`, `portals` выбирается заново **только
  при срабатывании таймера ротации** с учётом **весов** и **баланса сложности**
  (см. [`modifier_picker.py`](#как-работает-выбор-модификаторов)). Внешние
  рестарты (обновления системы, ребут, падение) применяют **ту же** комбинацию —
  см. [«Механизм ротации»](#механизм-ротации-когда-меняется-сложность).
- ⚖️ **Сбалансированность** — суммарный difficulty score комбинации держится в
  заданном диапазоне (`difficulty_range`), поэтому «лёгкие» и «сложные» дни
  перемежаются, а не выпадают подряд.
- 📊 **`--stats N`** — симуляция распределения выбора, чтобы настраивать веса
  осознанно, без реальных перезапусков.
- 🔧 **Фиксированный набор `setkeys`** (`nomap`, `passivemobs` и т.п.), который
  задаётся в одном месте и применяется ко всем запускам.
- 💾 **Корректное сохранение мира при перезапуске** через `KillSignal=SIGINT`
  и `TimeoutStopSec` — без BepInEx-модов и RCON.
- 📨 **Уведомления в Telegram** с описанием активных модификаторов (на русском,
  по материалам [русской вики](https://ru.valheim.weirdgloop.org/w/Модификаторы_мира)).
  Отправка через внешний SOCKS5-прокси (`socks5h://`) — DNS резолвится на стороне
  прокси, что обходит блокировку в РФ. Сообщение закрепляется в чате, а
  предыдущее закрепление автоматически снимается.
- 🧠 **ИИ-комментарий к ротации** (опционально) — к сообщению добавляется короткий
  шутливый разбор новой сложности, сгенерированный через OpenAI-совместимый API
  (DeepSeek / Open WebUI / OpenAI). См. [«ИИ-комментарий»](#ии-комментарий-к-ротации).

## Требования

- Ubuntu 24.04 (тестировалось), пользователь `steam`, сервер Valheim 1.0+.
- `jq`, `python3`, `python3-requests`, `python3-socks`.
- `steamcmd` в `/usr/games/steamcmd`.
- (для Telegram) внешний SOCKS5-прокси за пределами РФ.

```bash
sudo apt install jq python3 python3-requests python3-socks
```

## Установка

```bash
# 1. Клонируем репозиторий РЯДОМ с папкой сервера (не внутрь неё)
sudo git clone <repo-url> /home/steam/valheim-config
cd /home/steam/valheim-config

# 2. Первичный деплой: раскладывает файлы, ставит юниты, генерирует таймер
sudo ./deploy.sh

# 3. Настраиваем Telegram
sudo -u steam nano /home/steam/Valheim-Server/tg.env
# заполняем TG_BOT_TOKEN, TG_CHAT_ID и TG_PROXY_URL

# 4. Запускаем сервер и таймер
sudo systemctl enable --now valheim-server.service
sudo systemctl enable --now valheim-server-rotate.timer
```

После первого запуска сервис применит случайные модификаторы, запишет их в
`last_modifiers.json` и отправит уведомление в Telegram (если токен настроен).

## Устройство проекта

| Файл | Роль |
| :--- | :--- |
| `modifiers.json` | Пул значений с **весами**, блок `balance` (difficulty scores, диапазон), фиксированный набор `setkeys`, время ротации |
| `modifier_descriptions.json` | Справочник «код → название и объяснение по-русски» для Telegram |
| `modifier_picker.py` | Взвешенный выбор + проверка difficulty score; режим `--stats` и функция `validate_config` |
| `start_valheim.sh` | Применяет модификаторы и запускает сервер через `exec`. Новую комбинацию генерирует **только** при маркере ротации; иначе применяет сохранённую `last_modifiers.json` |
| `send_tg.py` | Читает `last_modifiers.json` + `modifier_descriptions.json`, генерирует ИИ-комментарий (если настроен), отправляет сообщение, закрепляет его и открепляет предыдущее (id — в `telegram_state.json`) |
| `apply-schedule.sh` | Генерирует `valheim-server-rotate.timer` из шаблона по `restart_time` из JSON |
| `deploy.sh` | Валидирует конфиг, копирует файлы в `/home/steam/Valheim-Server/`, ставит юниты, вызывает `apply-schedule.sh` |
| `systemd/valheim-server.service` | Основной сервис: SteamCMD update → обёртка → сервер. Без `ExecStartPost` (не шлёт TG, не меняет сложность при обычном старте) |
| `systemd/valheim-server-rotate.service` | Ротация: `stop` → маркер `/run/valheim-rotate.flag` → `start`, затем `ExecStartPost` с уведомлением |
| `systemd/valheim-server-rotate.timer.template` | Шаблон таймера с плейсхолдером `__RESTART_TIME__` |

Runtime-файлы, которые **не коммитятся** и создаются на сервере:

- `/home/steam/Valheim-Server/last_modifiers.json` — что реально выбралось при последнем старте.
- `/home/steam/Valheim-Server/telegram_state.json` — `pinned_message_id` последнего закреплённого сообщения (для открепления предыдущего при ротации).
- `/home/steam/Valheim-Server/tg.env` — секреты Telegram и ключ OpenAI.

## Настройка модификаторов

Редактируйте `modifiers.json`. Каждому значению задан **вес** — чем больше
число, тем чаще оно выпадает. `normal` — это явный ключ в пуле; при передаче в
сервер `start_valheim.sh` пропускает его, потому что «Normal» в Valheim — это
отсутствие аргумента `-modifier`, а не отдельное значение.

### Веса и difficulty score

Пул каждого модификатора — словарь `{ значение: вес }`. Вероятность выбрать
значение — это его вес, делённый на сумму весов **этого** модификатора. Веса
независимы между модификаторами и не обязаны в сумме давать 100.

Помимо весов у каждого значения есть **difficulty score** в блоке
`balance.scores` — условная оценка «насколько это меняет сложность». Score
комбинации — сумма score всех выбранных значений. `modifier_picker.py` делает
взвешенный выбор, и если суммарный score попал в `balance.difficulty_range`
(например `[-1, 1]`), комбинация принимается; иначе выбор повторяется, до
`max_attempts` попыток.

Так «интересные», но редкие по весам значения не выпадают подряд: тяжёлый день
(`veryhard` бой + `hardcore` смерть) почти наверняка выйдет за верхнюю границу,
и пикер перебросает его в более сбалансированную комбинацию.

Если после `max_attempts` попыток ничего не попало в диапазон, срабатывает
**fallback** — все модификаторы становятся `normal` (score `0.0`). Именно
поэтому `normal` обязан быть в каждом пуле; `validate_config` проверяет это
(категория `no_normal_for_fallback`).

### Как работает выбор модификаторов

Логика вынесена в `modifier_picker.py` и не зависит от systemd:

1. **`weighted_pick(weights)`** — взвешенный выбор одного значения из пула.
2. **`difficulty(combo, scores)`** — сумма score по всем модификаторам
   (значения без явного score считаются нейтральными, `0.0`).
3. **`pick_balanced(...)`** — до `max_attempts` раз собирает комбинацию и
   возвращает первую, чей score попал в `[lo, hi]`; иначе fallback на `normal`.

При ротации `start_valheim.sh` вызывает пикер, получает JSON-комбинацию,
атомарно пишет её в `last_modifiers.json` (с `timestamp`, `_difficulty_score` и
`_attempts`), собирает аргументы `-modifier <имя> <значение>` для всех
значений, **кроме** `normal`, добавляет `-setkey` для каждого элемента
`setkeys[]` и `exec`-ом запускает `start_server_configured.sh`.

Пикер вызывается **только при наличии маркера `/run/valheim-rotate.flag`**
(создаёт `valheim-server-rotate.service`). При любом другом старте применяется
уже сохранённая `last_modifiers.json` — см.
[«Механизм ротации»](#механизм-ротации-когда-меняется-сложность).

```json
{
  "schedule": { "restart_time": "05:00" },
  "pool": {
    "combat":       { "easy": 15, "normal": 20, "hard": 30, "veryhard": 15 },
    "deathpenalty": { "casual": 10, "veryeasy": 15, "easy": 20, "normal": 30, "hard": 15 },
    "resources":    { "muchless": 10, "less": 20, "normal": 40, "more": 20, "muchmore": 10 },
    "raids":        { "none": 5, "muchless": 10, "normal": 30, "more": 20, "muchmore": 10 },
    "portals":      { "casual": 5, "normal": 30, "hard": 15, "veryhard": 5 }
  },
  "balance": {
    "difficulty_range": [-1, 1],
    "max_attempts": 100,
    "scores": {
      "combat":       { "easy": -2, "normal": 0, "hard": 0.5, "veryhard": 2 },
      "deathpenalty": { "casual": -3, "veryeasy": -2, "easy": -0.5, "normal": 0, "hard": 2, "hardcore": 3 },
      "resources":    { "muchmore": -2, "more": -1, "normal": 0, "less": 0.5, "muchless": 1 },
      "raids":        { "none": -2, "muchless": -1, "normal": 0, "more": 0.5, "muchmore": 1.5 },
      "portals":      { "casual": -2, "normal": 0, "hard": 0.5, "veryhard": 2 }
    }
  },
  "setkeys": []
}
```

### Допустимые значения

| Модификатор | Валидные значения |
| :--- | :--- |
| `combat` | `veryeasy`, `easy`, `normal`, `hard`, `veryhard` |
| `deathpenalty` | `casual`, `veryeasy`, `easy`, `normal`, `hard`, `hardcore` |
| `resources` | `muchless`, `less`, `normal`, `more`, `muchmore`, `most` |
| `raids` | `none`, `muchless`, `less`, `normal`, `more`, `muchmore` |
| `portals` | `casual`, `normal`, `hard`, `veryhard` |

«Normal» — это явное значение `normal` в пуле; в аргументах сервера оно **не**
передаётся. Значения пишутся **слитно и в нижнем регистре** (`veryhard`,
`muchmore`), иначе сервер молча проигнорирует аргумент.

### Setkeys (фиксированный набор)

Массив `setkeys` применяется **ко всем** запускам без рандомизации. Допустимые
значения:

| `setkey` | Что включает |
| :--- | :--- |
| `nobuildcost` | Бесплатное строительство (рецепты всё равно нужно открывать) |
| `playerevents` | Рейды привязаны к прогрессу каждого игрока, а не к общему прогрессу мира |
| `passivemobs` | Враги атакуют только в ответ |
| `nomap` | Полное отключение карты и миникарты |

Пустой массив `[]` = не применять ни одного флага.

### Время ротации

`schedule.restart_time` — время в формате `HH:MM` (24-часовой). Изменение не
требует полного `deploy.sh`:

```bash
sudo -u steam nano /home/steam/Valheim-Server/modifiers.json
# меняем "restart_time": "05:00" на нужное

sudo /home/steam/valheim-config/apply-schedule.sh
```

Скрипт проверит формат, сгенерирует новый `.timer`, сделает `daemon-reload` и
перезапустит таймер. `systemctl list-timers` покажет новую дату `NEXT`.

### Настройка весов: `--stats`

Чтобы подобрать веса осознанно, не перезапуская сервер, используйте симуляцию:

```bash
python3 modifier_picker.py modifiers.json --stats 20000
```

Скрипт прогоняет выбор `N` раз и печатает по каждому модификатору:

- **picked%** — как часто значение выбиралось взвешенным пикером (на любой
  попытке) — примерно пропорционально заданным весам;
- **accepted%** — как часто значение попадало в итоговую (принятую) комбинацию;
- **rejected%** — как часто выбор с этим значением отбраковывался
  `difficulty_range`.

В конце — строка **`Fallback: …%`** и гистограмма распределения difficulty
score. Хороший конфиг: `fallback_pct ≈ 0.00%` и симметричное распределение
вокруг центра диапазона. Большой `fallback_pct` или перекос — признак того, что
`difficulty_range` слишком узок относительно разброса score: расширьте диапазон
или подправьте `scores`.

`--stats` работает автономно (не трогает сервер, не пишет файлов) и безопасен
на машине разработчика.

### Валидация конфига

`validate_config(config)` возвращает словарь `{категория: [детали]}`; пустой
словарь = конфиг валиден. Функция вызывается **автоматически внутри
`deploy.sh`** — при проблемах деплой прерывается с ненулевым кодом. Проверить
вручную:

```bash
python3 -c "import json; from modifier_picker import validate_config as v; print(v(json.load(open('modifiers.json'))))"
```

Категории проблем:

| Категория | Что значит |
| :--- | :--- |
| `structure` | Нет обязательных полей (`pool`, `difficulty_range`) или диапазон некорректен |
| `empty_pool` | У модификатора пустой пул |
| `zero_total_weight` | Сумма весов модификатора `<= 0` |
| `zero_weight_values` | Значения с весом `<= 0` — никогда не выберутся |
| `missing_scores` | У значения пула нет score в `balance.scores` |
| `unreachable` | Значение не помещается в `difficulty_range` ни в одной комбинации |
| `no_normal_for_fallback` | В пуле нет `normal` — fallback не сработает |

Добавляя новое значение, всегда прогоняйте `validate_config` + `--stats`.

## Требование к `start_server_configured.sh`

Обёртка `start_valheim.sh` вызывает ваш существующий скрипт запуска:

```bash
exec ./start_server_configured.sh "${ARGS[@]}"
```

Убедитесь, что внутри `start_server_configured.sh` есть `"$@"` в строке запуска
`valheim_server.x86_64`, иначе аргументы не дойдут до сервера:

```bash
exec /home/steam/Valheim-Server/valheim_server.x86_64 \
    -name "Server" \
    -port 2456 \
    -world "Ololo" \
    -password "..." \
    -public 0 \
    -logFile /home/steam/Valheim-Server/valheim-server.log \
    "$@"
```

Без `exec` перед бинарником `SIGINT` может не дойти до `valheim_server` в
нестандартных конфигурациях systemd, и мир не сохранится. С `exec` бинарник
становится главным процессом сервиса.

## Сохранение мира при остановке

Valheim сохраняет мир при получении `SIGINT`, но **не** при `SIGTERM`
(дефолт systemd). В `valheim-server.service` это учтено:

```ini
KillSignal=SIGINT
TimeoutStopSec=120
```

`TimeoutStopSec=120` даёт серверу до двух минут на запись мира. Без
`KillSignal=SIGINT` `systemctl restart` завершит процесс аварийно, и вы
потеряете весь прогресс с последнего автосохранения.

## Механизм ротации: когда меняется сложность

Сложность меняется **только** в результате работы
`valheim-server-rotate.service`. Это гарантируется маркером ротации:

1. `valheim-server-rotate.service` (по таймеру или вручную) выполняет
   `systemctl stop valheim-server` — сервер корректно сохраняет мир;
2. создаёт маркер-файл `/run/valheim-rotate.flag`;
3. `systemctl start valheim-server`;
4. `start_valheim.sh` видит маркер → вызывает `modifier_picker.py`, генерирует
   **новую** комбинацию, пишет её в `last_modifiers.json` и удаляет маркер;
5. `ExecStartPost` в `valheim-server-rotate.service` отправляет сообщение в
   Telegram.

Если маркера нет (обычный старт), `start_valheim.sh` **не** запускает пикер, а
читает уже сохранённую `last_modifiers.json` и применяет ту же комбинацию. Это
касается:

- рестарта от `needrestart` после обновления `libc6` и других системных
  библиотек (как при `unattended-upgrades`);
- перезагрузки хоста (boot) — маркер в `/run` (tmpfs) при этом исчезает,
  поэтому ребут не считается ротацией;
- ручного `systemctl restart valheim-server`;
- автоматического `Restart=on-abnormal` после падения процесса.

Во всех этих случаях сложность **не меняется**, а Telegram-сообщение **не**
отправляется. Единственный «особый» случай — самый первый старт, когда
`last_modifiers.json` ещё не существует: тогда комбинация генерируется один раз,
чтобы серверу было что применить.

Маркер живёт в `/run` (tmpfs) — он автоматически исчезает при перезагрузке, и
«зависший» маркер после неудачной ротации не переживёт ребут.

### Как запустить ротацию вручную

```bash
sudo systemctl start valheim-server-rotate.service   # = стоп → маркер → старт → TG
```

Не используйте для смены сложности `systemctl restart valheim-server` — это лишь
перезапустит сервер с **текущей** комбинацией.

## Telegram через SOCKS5-прокси

Скрипт `send_tg.py` использует библиотеку `requests`, которая поддерживает
HTTP- и SOCKS-прокси. Для SOCKS нужен пакет **PySocks** — в Ubuntu он
ставится из apt:

```bash
sudo apt install python3-socks
```

Это покрывает системный Python (`/usr/bin/python3`), которым запускается
`send_tg.py` из systemd. Если используете venv — ставьте `pip install 'requests[socks]'`
внутрь venv.

### Настройка `tg.env`

В `/home/steam/Valheim-Server/tg.env` укажите прокси. **Схема `socks5h://`
обязательна** — её нужно дописать самим, даже если у вас есть только IP, порт
и учётные данные:

```env
# Без авторизации
TG_PROXY_URL=socks5h://142.25.125.255:31471

# С логином и паролем
TG_PROXY_URL=socks5h://user:password@142.25.125.255:31471
```

**Почему `socks5h`, а не `socks5`**: `h` = hostname резолвится **на стороне
прокси**. С `socks5://` ваш сервер сначала резолвит `api.telegram.org` через
локальный DNS, который в РФ отдаёт подменённый IP — и вы получите `302` от
nginx-заглушки вместо ответа Telegram.

**Если в пароле есть `@`, `:`, `/`, `?`, `#`** — percent-encode их:

| Символ | Замена |
| :--- | :--- |
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `?` | `%3F` |
| `#` | `%23` |

Проверить кодирование:

```bash
python3 -c "from urllib.parse import quote; print(quote('p@ss:w0rd', safe=''))"
```

### Проверка перед запуском

```bash
# 1. PySocks установлен
python3 -c "import socks; print('PySocks OK')"

# 2. Прокси пропускает Bot API (подставьте свои значения)
read -rsp "Proxy: " P
read -rsp "Bot token: " T
echo
curl -sS --socks5-hostname "$P" "https://api.telegram.org/bot${T}/getMe"
echo
unset P T
```

Ожидаемый ответ — `{"ok":true,"result":{...}}`. Если получили `curl: (97) ... (2)`,
проверьте логин/пароль (и percent-encode спецсимволов). Если `302` от nginx —
скорее всего, `$P` пуст и запрос ушёл напрямую.

### Частые ошибки

| Симптом | Причина |
| :--- | :--- |
| `InvalidSchema: No connection adapters were found for 'socks5h://...'` | Не установлен PySocks. `sudo apt install python3-socks` |
| `ОШИБКА: TG_PROXY_URL должен начинаться со схемы` | Забыли `socks5h://` в `tg.env` |
| `curl: (97) Can't complete SOCKS5 connection ... (2)` | Неверный логин/пароль, либо спецсимволы в пароле не закодированы |
| `302 Found` от `nginx` | Запрос ушёл напрямую (пустой `TG_PROXY_URL` или `$P`), DNS подменён |

### Когда отправляется сообщение

Уведомление вызывается из `ExecStartPost=` **`valheim-server-rotate.service`**,
то есть **только при реальной ротации** — когда сработал таймер (05:00 или
catch-up после пропуска) или вы вручную запустили ротацию.

Обычные рестарты `valheim-server.service` (needrestart после обновления `libc`,
автообновления, ребут хоста, `Restart=on-abnormal` при падении) **не** шлют
сообщение — у основного сервиса `ExecStartPost` больше нет. Сложность при таких
стартах тоже не меняется (применяется сохранённая `last_modifiers.json`).

Префикс `-` в `ExecStartPost=` означает, что провал `send_tg.py` (нет `tg.env`,
прокси недоступен, `last_modifiers.json` отсутствует) **не** переведёт юнит в
состояние `failed`. Ошибки видны в `journalctl -u valheim-server-rotate.service`
— они не влияют на жизненный цикл сервиса, но полезны для диагностики.

### Открепление предыдущего сообщения

Чтобы в чате всегда было закреплено только актуальное объявление, скрипт
`send_tg.py` после закрепления нового сообщения открепляет предыдущее.
Идентификатор последнего закрепления хранится в
`/home/steam/Valheim-Server/telegram_state.json`:

```json
{ "pinned_message_id": 12345 }
```

Логика по шагам: отправить сообщение → закрепить новое → открепить старое
(`unpinChatMessage` с конкретным `message_id`) → сохранить новый id. Порядок
специально такой («сначала закрепить, потом открепить»): если открепление не
удастся, новое всё равно останется закреплённым. Сбой открепления (например,
сообщение удалили вручную) — только `ВНИМАНИЕ`, не ошибка.

> Бот должен иметь право `can_pin_messages` в чате. `unpinChatMessage` вызывается
> с явным `message_id`, чтобы не снять чужие закрепления.

## ИИ-комментарий к ротации

Если задан `OPENAI_API_KEY`, к сообщению добавляется короткий шутливый абзац —
разбор новой сложности с контекстом по Valheim. Генерация идёт через
**OpenAI-совместимый** протокол (`POST {OPENAI_BASE_URL}/v1/chat/completions`),
поэтому подходит любой совместимый провайдер: DeepSeek, Open WebUI, сам OpenAI.

Переменные окружения (в `tg.env`):

```env
# Включает ИИ-комментарий; если пусто/не задан — анализ не генерируется.
OPENAI_API_KEY=sk-...

# Базовый URL API (по умолчанию — DeepSeek).
#   DeepSeek:   https://api.deepseek.com
#   OpenAI:     https://api.openai.com
#   Open WebUI: https://ваш-хост/api   (или .../openai)
OPENAI_BASE_URL=https://api.deepseek.com

# Модель (по умолчанию deepseek-chat — DeepSeek-V3, дешёвая, хорошо пишет по-русски).
OPENAI_MODEL=deepseek-chat

# Предел длины ИИ-абзаца в символах (по умолчанию 320).
OPENAI_ANALYSIS_MAX_CHARS=320
```

Поведение:

- **Нет `OPENAI_API_KEY`** → анализ молча не генерируется, сообщение уходит как
  раньше (fail-soft, обратная совместимость).
- **Ошибка API** (таймаут, 401, rate limit, пустой ответ) → только `ВНИМАНИЕ` в
  лог, сообщение уходит **без** анализа. Ротация не страдает.
- **Превышение лимита длины** → текст обрезается по границе слова с `…`.
- Запрос к OpenAI идёт **напрямую** (без SOCKS-прокси), в отличие от Telegram.
  Убедитесь, что у сервера есть сетевой доступ к `OPENAI_BASE_URL`.
- В модель передаются **только** названия и описания модификаторов — никаких
  секретов, IP или имён игроков.

Рекомендуемые параметры вызова зашиты в код: `temperature=0.9` (для вариативности
и юмора), `max_tokens=220` (страховка сверх лимита символов). Стоимость на
`deepseek-chat` — доли цента за сутки (один запрос в день).

## Бэкапы

В этот репозиторий скрипт бэкапа не входит. Минимум — ручной архив всей папки
мира (не отдельных файлов: с версии 1.0 мир — это директория с `.fwl2`, `.db2`
и `.chunks`):

```bash
sudo systemctl stop valheim-server
sudo -u steam tar -czf ~steam/valheim_worlds_$(date +%F_%H-%M).tar.gz \
    -C /home/steam/.config/unity3d/IronGate/Valheim worlds_local
sudo systemctl start valheim-server
```

Остановка перед `tar` гарантирует консистентность; при `KillSignal=SIGINT`
сервер корректно сохранит мир перед выходом. Для production-сценария стоит
добавить отдельный systemd-таймер с ежедневным архивом и ротацией (например,
хранить 14 дней) — как отдельная задача.

## Диагностика

```bash
# Состояние сервиса
systemctl status valheim-server.service

# Логи запуска (включая вывод start_valheim.sh с выбранными модификаторами)
journalctl -u valheim-server.service -n 100 --no-pager

# Что реально выбралось в последний раз
cat /home/steam/Valheim-Server/last_modifiers.json | jq

# Проверить аргументы, переданные бинарнику
ps -ef | grep valheim_server

# Ближайшее срабатывание таймера
systemctl list-timers valheim-server-rotate.timer --no-pager

# Логи ротации и Telegram
journalctl -u valheim-server-rotate.service -n 50 --no-pager
```

Если модификаторы не применяются — проверьте `ps -ef | grep valheim_server`.
В строке процесса должны быть видны `-modifier combat ...` и `-setkey ...`.
Если их нет — `start_server_configured.sh` не пробрасывает `"$@"`.

## Обновление

```bash
cd /home/steam/valheim-config
sudo git pull
sudo ./deploy.sh
sudo systemctl restart valheim-server.service
```

`deploy.sh` идемпотентен: перезаписывает файлы, обновляет юниты, вызывает
`apply-schedule.sh` (пересобирает таймер из JSON), но **не трогает** `tg.env`
и `last_modifiers.json`. Юнит `valheim-server.service` не перезапускается
автоматически — это осознанно: `restart` делается руками, чтобы контролировать
момент перезапуска.

`sudo systemctl restart valheim-server` применяет **текущую** комбинацию из
`last_modifiers.json` и **не** меняет сложность. Чтобы сменить модификаторы
сразу, запустите не `restart`, а ротацию:

```bash
sudo systemctl start valheim-server-rotate.service
```

## Структура репозитория

```
valheim-daily-modifiers/
├── .gitignore
├── LICENSE
├── README.md
├── modifiers.json
├── modifier_descriptions.json
├── modifier_picker.py
├── start_valheim.sh
├── send_tg.py
├── apply-schedule.sh
├── deploy.sh
├── tg.env.example
└── systemd/
    ├── valheim-server.service
    ├── valheim-server-rotate.service
    └── valheim-server-rotate.timer.template
```

## Лицензия

MIT — см. [LICENSE](LICENSE).