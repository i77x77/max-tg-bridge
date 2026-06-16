# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A bidirectional bridge between [MAX messenger](https://max.ru) and Telegram. Incoming MAX messages are forwarded to a Telegram supergroup as forum topics (one topic per MAX chat). Replies sent from Telegram back into those topics are forwarded to the corresponding MAX chat.

## Running

```bash
python main.py
```

Requires a `.env` file (see `.env.example`):
- `MAX_PHONE` — phone number for the MAX account
- `TG_BOT_TOKEN` — Telegram bot token
- `TG_GROUP_ID` — numeric ID of the Telegram supergroup (must have Topics enabled)

On first run the bot authenticates interactively via `pymax` and creates a session at `cache/session.db`. All MAX chats are synced to Telegram forum topics on startup, with the mapping persisted at `cache/topics.json`.

## Dependencies

Install with pip:
```bash
pip install aiogram pymax python-dotenv
```

No build step, no test suite.

## Architecture

Everything lives in `main.py`. The two async runtimes run concurrently via `asyncio.gather`:
- **`pymax.Client`** — listens for MAX events via `@client.on_message()` and `@client.on_start()`
- **`aiogram.Dispatcher`** — listens for Telegram messages via `@dp.message(...)`

**MAX → TG flow:** `on_max_message` resolves the MAX chat title, calls `get_or_create_topic` to find or create the Telegram forum thread, then forwards text/photos. Videos and files are sent as label placeholders (pymax doesn't expose direct download URLs for those types).

**TG → MAX flow:** `on_tg_message` filters to messages in `TG_GROUP_ID` that belong to a known thread, downloads any attachment from Telegram, and calls `client.send_message` on the corresponding MAX chat.

**Topic mapping** is a plain JSON dict (`str(max_chat_id) → tg_thread_id`) loaded at startup and written on every new topic creation.

**Chat title resolution** (`_chat_title`) prefers `chat.title`, then tries to resolve the other participant's name from `pymax`'s user cache, falling back to a service-account label.
