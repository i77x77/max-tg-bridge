# MAX → Telegram Bridge

Двусторонний мост между мессенджером [MAX](https://max.ru) и Telegram.

- Входящие сообщения из MAX появляются в Telegram-супергруппе как отдельные темы (одна тема = один MAX-чат).
- Ответы из Telegram отправляются обратно в соответствующий MAX-чат.

Поддерживается пересылка текста, фото и файлов в обоих направлениях.

## Требования

- Python 3.11+
- Telegram-бот с правами администратора в супергруппе с включёнными темами (Topics)
- Аккаунт MAX

## Быстрый старт (локально)

```bash
git clone <repo-url>
cd max-tg-bridge

pip install aiogram pymax python-dotenv

cp .env.example .env
# отредактируйте .env
python main.py
```

При первом запуске `pymax` запросит код подтверждения из MAX — введите его в терминал. Сессия сохраняется в `cache/session.db`, повторная авторизация не нужна.

## Переменные окружения

| Переменная     | Пример                          | Описание                                      |
|----------------|---------------------------------|-----------------------------------------------|
| `MAX_PHONE`    | `+79990000000`                  | Номер телефона MAX-аккаунта                   |
| `TG_BOT_TOKEN` | `1234567890:AAF...`             | Токен бота ([@BotFather](https://t.me/BotFather)) |
| `TG_GROUP_ID`  | `-100123456789`                 | ID супергруппы Telegram                       |

Узнать `TG_GROUP_ID` можно, добавив бота [@username_to_id_bot](https://t.me/username_to_id_bot) в группу или посмотрев через веб-версию Telegram.

## Деплой на сервер (systemd)

### 1. Подготовка

```bash
# На сервере
sudo apt update && sudo apt install -y python3 python3-pip git

git clone <repo-url> /opt/max-tg-bridge
cd /opt/max-tg-bridge
pip3 install aiogram pymax python-dotenv

cp .env.example .env
nano .env   # заполните переменные
```

### 2. Первый запуск — авторизация в MAX

Первый раз нужно запустить вручную, чтобы ввести код из MAX:

```bash
cd /opt/max-tg-bridge
python3 main.py
# Введите код подтверждения, дождитесь "Sync done, watching for messages..."
# Ctrl+C
```

После этого сессия сохранена в `cache/session.db` и бот больше не будет спрашивать код.

### 3. Systemd-сервис

Создайте файл `/etc/systemd/system/max-tg-bridge.service`:

```ini
[Unit]
Description=MAX to Telegram Bridge
After=network.target

[Service]
WorkingDirectory=/opt/max-tg-bridge
ExecStart=/usr/bin/python3 main.py
Restart=on-failure
RestartSec=10
EnvironmentFile=/opt/max-tg-bridge/.env
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable max-tg-bridge
sudo systemctl start max-tg-bridge

# Проверить статус и логи:
sudo systemctl status max-tg-bridge
sudo journalctl -u max-tg-bridge -f
```

### Обновление

```bash
cd /opt/max-tg-bridge
git pull
sudo systemctl restart max-tg-bridge
```

## Файлы состояния

| Путь                  | Содержимое                                      |
|-----------------------|-------------------------------------------------|
| `cache/session.db`    | Сессия MAX (не удалять — потребует переавторизации) |
| `cache/topics.json`   | Маппинг MAX chat ID → Telegram thread ID        |

## Ограничения

- Видео и прочие файлы из MAX пересылаются только как текстовые плейсхолдеры (`[видео]`, `[файл]`) — pymax не предоставляет прямых ссылок для скачивания этих типов.
- Бот игнорирует свои собственные сообщения в Telegram (фильтр `~F.from_user.is_bot`).
