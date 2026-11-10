# valheim-daily-modifiers

Набор скриптов и systemd-юнитов для выделенного сервера Valheim (Ubuntu 24.04):

- 🎲 **Ежедневная случайная ротация world modifiers** — комбинация `combat`,
  `deathpenalty`, `resources`, `raids`, `portals` выбирается из пула заново
  при каждом перезапуске.
- 🔧 **Фиксированный набор `setkeys`** (`nomap`, `passivemobs` и т.п.), который
  задаётся в одном месте и применяется ко всем запускам.
- 💾 **Корректное сохранение мира при перезапуске** через `KillSignal=SIGINT`
  и `TimeoutStopSec` — без BepInEx-модов и RCON.
- 📨 **Уведомления в Telegram** с описанием активных модификаторов (на русском,
  по материалам [русской вики](https://ru.valheim.weirdgloop.org/w/Модификаторы_мира)).
- 🌐 **Обход блокировки Telegram в РФ** через локальный прокси `tgwsapiproxy` +
  Cloudflare Worker (трафик маскируется под `*.workers.dev`).

## Требования

- Ubuntu 24.04 (тестировалось), пользователь `steam`, сервер Valheim 1.0+.
- `jq`, `python3`, `python3-requests`.
- `steamcmd` в `/usr/games/steamcmd`.
- (опционально, для Telegram) `tgwsapiproxy` и развёрнутый Cloudflare Worker.

```bash
sudo apt install jq python3 python3-requests
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
| `modifiers.json` | Пул допустимых значений модификаторов, фиксированный набор `setkeys`, время ротации |
| `modifier_descriptions.json` | Справочник «код → название и объяснение по-русски» для Telegram |
| `start_valheim.sh` | Выбирает случайные значения, пишет `last_modifiers.json`, запускает сервер через `exec` |
| `send_tg.py` | Читает `last_modifiers.json` + `modifier_descriptions.json`, отправляет сообщение через прокси |
| `apply-schedule.sh` | Генерирует `valheim-server-rotate.timer` из шаблона по `restart_time` из JSON |
| `deploy.sh` | Копирует файлы в `/home/steam/Valheim-Server/`, ставит юниты, вызывает `apply-schedule.sh` |
| `systemd/valheim-server.service` | Основной сервис: SteamCMD update → обёртка → `ExecStartPost` с уведомлением |
| `systemd/valheim-server-rotate.service` | Разовый `systemctl restart` основного сервиса |
| `systemd/valheim-server-rotate.timer.template` | Шаблон таймера с плейсхолдером `__RESTART_TIME__` |

Runtime-файлы, которые **не коммитятся** и создаются на сервере:

- `/home/steam/Valheim-Server/last_modifiers.json` — что реально выбралось при последнем старте.
- `/home/steam/Valheim-Server/tg.env` — секреты Telegram.

## Настройка модификаторов

Редактируйте `modifiers.json`. Пустая строка `""` в пуле означает **«не передавать
аргумент»** — это состояние «Normal» по умолчанию. В игре у ползунков четыре
метки, но в командной строке для «Normal» значения нет: `-modifier` принимает
только отклонения от стандарта.

```json
{
  "schedule": {
    "restart_time": "05:00"
  },
  "pool": {
    "combat":       ["veryeasy", "easy", "hard", "veryhard", ""],
    "deathpenalty": ["casual", "veryeasy", "easy", "hard", "hardcore", ""],
    "resources":    ["muchless", "less", "more", "muchmore", "most", ""],
    "raids":        ["none", "muchless", "less", "more", "muchmore", ""],
    "portals":      ["casual", "hard", "veryhard", ""]
  },
  "setkeys": []
}
```

### Допустимые значения

| Модификатор | Валидные значения | «Normal» через |
| :--- | :--- | :--- |
| `combat` | `veryeasy`, `easy`, `hard`, `veryhard` | `""` |
| `deathpenalty` | `casual`, `veryeasy`, `easy`, `hard`, `hardcore` | `""` |
| `resources` | `muchless`, `less`, `more`, `muchmore`, `most` | `""` |
| `raids` | `none`, `muchless`, `less`, `more`, `muchmore` | `""` |
| `portals` | `casual`, `hard`, `veryhard` | `""` |

Значения пишутся **слитно и в нижнем регистре** (`veryhard`, `muchmore`), иначе
сервер молча проигнорирует аргумент.

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

Уведомление вызывается из `ExecStartPost=` основного сервиса, то есть
**после каждого успешного запуска**, включая:

- ежедневный рестарт по таймеру (05:00 или catch-up после пропуска);
- ручной `systemctl restart valheim-server`;
- перезагрузку сервера (boot).

Если сервер упал сразу после старта — сообщение не уйдёт (проверка
`systemctl is-active --quiet`).

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
и `last_modifiers.json`.

## Структура репозитория

```
valheim-server-ops/
├── .gitignore
├── LICENSE
├── README.md
├── modifiers.json
├── modifier_descriptions.json
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