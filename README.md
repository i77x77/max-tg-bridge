# MAX → Telegram Bridge

Двусторонний мост между мессенджером [MAX](https://max.ru) и Telegram.

- Входящие сообщения из MAX появляются в Telegram-супергруппе как отдельные темы (одна тема = один MAX-чат).
- Ответы из Telegram отправляются обратно в соответствующий MAX-чат.

Поддерживается пересылка текста, фото и файлов в обоих направлениях.

## Требования

- Python 3.11+
- Telegram-бот с правами администратора в супергруппе с включёнными Topics
- Аккаунт MAX

---

## Развёртывание на сервере

### 1. Клонировать репозиторий

```bash
git clone https://github.com/i77x77/max-tg-bridge.git /root/max-tg-bridge
cd /root/max-tg-bridge
```

### 2. Создать виртуальное окружение и установить зависимости

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Настроить переменные окружения

```bash
cp .env.example .env
nano .env
```

| Переменная      | Пример              | Описание                                              |
|-----------------|---------------------|-------------------------------------------------------|
| `MAX_PHONE`     | `+79990000000`      | Номер телефона MAX-аккаунта                           |
| `TG_BOT_TOKEN`  | `1234567890:AAF...` | Токен бота ([@BotFather](https://t.me/BotFather))    |
| `TG_GROUP_ID`   | `-100123456789`     | ID супергруппы Telegram                               |
| `SYNC_ON_START` | `false`             | `true` — создать все топики при старте, `false` — по первому сообщению |

### 4. Первый запуск — авторизация в MAX

Нужно запустить вручную один раз, чтобы ввести код подтверждения из MAX:

```bash
source venv/bin/activate
python3 main.py
```

Введите код, дождитесь строки `watching for messages...` — затем `Ctrl+C`.

Сессия сохраняется в `cache/session.db` и повторная авторизация не нужна.

### 5. Создать systemd-сервис

```bash
nano /etc/systemd/system/max-tg-bridge.service
```

Содержимое файла:

```ini
[Unit]
Description=MAX to Telegram Bridge
After=network.target

[Service]
WorkingDirectory=/root/max-tg-bridge
ExecStart=/root/max-tg-bridge/venv/bin/python3 main.py
Restart=on-failure
RestartSec=10
EnvironmentFile=/root/max-tg-bridge/.env
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 6. Запустить и включить автозапуск

```bash
sudo systemctl daemon-reload
sudo systemctl enable max-tg-bridge
sudo systemctl start max-tg-bridge
```

Проверить статус:

```bash
sudo systemctl status max-tg-bridge
sudo journalctl -u max-tg-bridge -f
```

---

## Обновление

```bash
cd /root/max-tg-bridge
git pull
pip install -r requirements.txt
sudo systemctl restart max-tg-bridge
```

---

## Команды бота

Написать `/status` в Telegram-группе — бот ответит:

```
✅ Работает
⏱ Uptime: 2ч 15м 30с
💬 Чатов: 12
📨 Последнее сообщение из MAX: 3 мин назад
```

---

## Файлы состояния

| Путь                | Содержимое                                              |
|---------------------|---------------------------------------------------------|
| `cache/session.db`  | Сессия MAX (не удалять — потребует переавторизации)    |
| `cache/topics.json` | Маппинг MAX chat ID → Telegram thread ID               |

---

## Ограничения

- Видео и прочие файлы из MAX пересылаются как плейсхолдеры (`[видео]`, `[файл]`) — pymax не предоставляет прямых ссылок для скачивания.
