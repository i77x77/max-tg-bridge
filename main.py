import asyncio
import json
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Message as TGMessage
from aiogram.types import URLInputFile
from dotenv import load_dotenv
from pymax import Client
from pymax.files import File as MaxFile
from pymax.files import Photo as MaxPhoto
from pymax.types import FileAttachment, Message, PhotoAttachment, VideoAttachment

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

MAX_PHONE = os.getenv("MAX_PHONE")
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_GROUP_ID = int(os.getenv("TG_GROUP_ID", "0"))
SYNC_ON_START = os.getenv("SYNC_ON_START", "true").lower() in ("1", "true", "yes")

MAPPING_FILE = Path("cache/topics.json")

bot = Bot(token=TG_TOKEN)
dp = Dispatcher()
client = Client(phone=MAX_PHONE, work_dir="cache", session_name="session.db")

# max_chat_id (str) -> tg_thread_id (int)
_mapping: dict[str, int] = {}


def _load_mapping() -> None:
    if MAPPING_FILE.exists():
        _mapping.update(json.loads(MAPPING_FILE.read_text()))


def _save_mapping() -> None:
    MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
    MAPPING_FILE.write_text(json.dumps(_mapping, indent=2))


def _thread_to_max_chat(tg_thread_id: int) -> int | None:
    for max_id, thread_id in _mapping.items():
        if thread_id == tg_thread_id:
            return int(max_id)
    return None


async def get_or_create_topic(max_chat_id: int, title: str) -> int:
    key = str(max_chat_id)
    if key in _mapping:
        return _mapping[key]

    name = title[:128] or f"Чат {max_chat_id}"
    logger.info("Creating topic for MAX chat %s: %s", max_chat_id, name)
    while True:
        try:
            topic = await bot.create_forum_topic(TG_GROUP_ID, name)
            break
        except TelegramRetryAfter as e:
            logger.info("Rate limit, waiting %s sec...", e.retry_after)
            await asyncio.sleep(e.retry_after)

    thread_id = topic.message_thread_id
    _mapping[key] = thread_id
    _save_mapping()
    logger.info("Topic created: thread_id=%s for max_chat_id=%s", thread_id, max_chat_id)
    return thread_id


def _is_personal_chat(max_chat_id: int) -> bool:
    chats = client.chats or []
    my_id = client.me.contact.id if client.me else None
    for chat in chats:
        if chat.id == max_chat_id:
            return not chat.title
    return False


def _user_display_name(user) -> str | None:
    if not user:
        return None
    # Сначала пробуем собрать из first+last — они надёжнее поля name
    for n in user.names or []:
        parts = [n.first_name, n.last_name]
        full = " ".join(p for p in parts if p)
        if full:
            return full
        if n.name:
            return n.name
    # Запасной вариант — телефон или login
    if user.phone:
        return f"+{user.phone}"
    if user.link:
        return user.link.split("/")[-1]  # @username из ссылки
    return None


async def _chat_title(max_chat_id: int, sender_id: int | None = None) -> str:
    chats = client.chats or []
    my_id = client.me.contact.id if client.me else None
    for chat in chats:
        if chat.id != max_chat_id:
            continue
        if chat.title:
            return chat.title
        other_ids = [uid for uid in chat.participants if uid != my_id]
        for uid in other_ids:
            user = client.get_cached_user(uid)
            if user is None:
                try:
                    user = await client.get_user(uid)
                except Exception:
                    pass
            name = _user_display_name(user)
            if name:
                return name
        return f"Сервис {max_chat_id}"

    # Чат ещё не в кеше — пробуем имя отправителя
    if sender_id and sender_id != my_id:
        name = await _sender_name(sender_id)
        if name and not name.isdigit():
            return name
    return f"Чат {max_chat_id}"


async def _sender_name(sender_id: int) -> str:
    user = client.get_cached_user(sender_id)
    if user is None:
        try:
            user = await client.get_user(sender_id)
        except Exception:
            pass
    return _user_display_name(user) or str(sender_id)


async def _sync_all_chats() -> None:
    chats = client.chats or []
    try:
        more = await client.fetch_chats()
        if more:
            chats = list({c.id: c for c in (chats + more)}.values())
    except Exception as e:
        logger.warning("fetch_chats failed: %s", e)

    logger.info("Syncing %d MAX chats to Telegram topics", len(chats))
    for chat in chats:
        title = await _chat_title(chat.id)
        try:
            await get_or_create_topic(chat.id, title)
            await asyncio.sleep(3)
        except Exception as e:
            logger.warning("Failed to create topic for %s (%s): %s", title, chat.id, e)


# ── MAX → TG ──────────────────────────────────────────────

@client.on_start()
async def on_start(c: Client) -> None:
    my_id = c.me.contact.id if c.me else "?"
    logger.info("MAX connected, my id=%s", my_id)
    _load_mapping()
    if SYNC_ON_START:
        await _sync_all_chats()
        logger.info("Sync done, watching for messages...")
    else:
        logger.info("Sync skipped (SYNC_ON_START=false), topics will be created on first message")


@client.on_message()
async def on_max_message(message: Message, c: Client) -> None:
    if message.chat_id is None:
        return

    # Пропускаем свои сообщения — они уже отправлены через TG→MAX
    my_id = c.me.contact.id if c.me else None
    if my_id and message.sender == my_id:
        return

    title = await _chat_title(message.chat_id, sender_id=message.sender)
    thread_id = await get_or_create_topic(message.chat_id, title)

    personal = _is_personal_chat(message.chat_id)
    if not personal:
        name = await _sender_name(message.sender) if message.sender else "Unknown"

    photos = [a for a in message.attaches if isinstance(a, PhotoAttachment)]
    videos = [a for a in message.attaches if isinstance(a, VideoAttachment)]
    files = [a for a in message.attaches if isinstance(a, FileAttachment)]
    has_media = bool(photos or videos or files)

    send_kw = {"chat_id": TG_GROUP_ID, "message_thread_id": thread_id}

    def _fmt(text: str | None, label: str | None = None) -> str:
        body = label or text or ""
        if personal:
            return body
        return f"{name}: {body}" if body else name

    try:
        if photos:
            caption = _fmt(message.text)
            await bot.send_photo(
                **send_kw,
                photo=URLInputFile(photos[0].base_url),
                caption=caption[:1024],
            )
            for photo in photos[1:]:
                await bot.send_photo(**send_kw, photo=URLInputFile(photo.base_url))
        elif message.text:
            await bot.send_message(**send_kw, text=_fmt(message.text))
        elif not has_media:
            return

        for v in videos:
            label = getattr(v, "file_name", None) or "видео"
            await bot.send_message(**send_kw, text=_fmt(None, f"[{label}]"))
        for f in files:
            label = getattr(f, "file_name", None) or "файл"
            await bot.send_message(**send_kw, text=_fmt(None, f"[{label}]"))

    except Exception as e:
        logger.error("Failed to forward message from %s: %s", title, e)


# ── TG → MAX ──────────────────────────────────────────────

@dp.message(F.chat.id == TG_GROUP_ID, F.message_thread_id.is_not(None), ~F.from_user.is_bot)
async def on_tg_message(msg: TGMessage) -> None:
    max_chat_id = _thread_to_max_chat(msg.message_thread_id)
    if max_chat_id is None:
        return

    text = msg.text or msg.caption or ""
    attachments = []

    try:
        if msg.photo:
            data = await bot.download(msg.photo[-1].file_id)
            attachments.append(MaxPhoto(raw=data.read(), name="photo.jpg"))

        elif msg.document:
            doc = msg.document
            data = await bot.download(doc.file_id)
            attachments.append(MaxFile(raw=data.read(), name=doc.file_name or "file"))

        elif msg.video:
            vid = msg.video
            data = await bot.download(vid.file_id)
            name = vid.file_name or "video.mp4"
            attachments.append(MaxFile(raw=data.read(), name=name))

    except Exception as e:
        logger.warning("Failed to download attachment: %s", e)

    if not text and not attachments:
        return

    try:
        await client.send_message(
            chat_id=max_chat_id,
            text=text,
            attachments=attachments or None,
        )
        logger.info("Sent to MAX chat %s: %s", max_chat_id, text[:50] or "[медиа]")
    except Exception as e:
        logger.error("Failed to send to MAX chat %s: %s", max_chat_id, e)


# ── запуск ────────────────────────────────────────────────

async def main() -> None:
    await asyncio.gather(
        client.start(),
        dp.start_polling(bot, allowed_updates=["message"]),
    )


if __name__ == "__main__":
    asyncio.run(main())
