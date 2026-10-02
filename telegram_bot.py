"""Telegram layer. Real Bot API, long polling. Zero agent logic in here.

All it does: receive message/file -> call agent.handle_message() -> send reply.
"""
from pathlib import Path

import config
import store
import tools

try:
    from telegram import Update
    from telegram.ext import (
        ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,
        filters,
    )
except ImportError:  # keeps the CLI harness usable without the lib
    ApplicationBuilder = None

MAX_FILE_BYTES = 20 * 1024 * 1024


async def _reply(update: Update, text: str) -> None:
    """Telegram caps messages at 4096 chars; split long ones safely."""
    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i + 4000])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != _allowed_chat():
        store.log_activity(f"Blocked unknown chat {update.effective_chat.id}")
        return
    await _reply(update, tools.status_text())


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, tools.status_text())


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = store.load_state()
    if not state.get("brief_path"):
        await _reply(update, "No brief yet — I generate it once onboarding is complete. "
                             "Send me the missing bits first! ☕")
        return
    await _reply(update, tools.brief_text())


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tasks = [t for t in store.load_tasks() if t["client_id"] == config.CLIENT_ID]
    if not tasks:
        await _reply(update, "No internal tasks created yet.")
        return
    lines = [f"**Internal tasks — {len(tasks)}**", ""]
    lines += [f"{i}. {t['title']}" for i, t in enumerate(tasks, 1)]
    await _reply(update, "\n".join(lines))


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config.ensure_dirs()
    store.save_state(store.blank_state(config.CLIENT_ID))
    store.save_tasks([])
    store.log_activity("Agency reset onboarding state (admin command)")
    await _reply(update, "State cleared. Starting fresh 👋")
    await _reply(update, __import__("agent").start_onboarding())


async def _download(obj, dest) -> int:
    """Download a Telegram file object to disk. Works on python-telegram-bot v21+/22."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    handle = await obj.get_file() if hasattr(obj, "get_file") else obj
    for attempt in (None, "download_as_bytearray", "download_to_custom_path", "download_to_drive"):
        try:
            if attempt is None:
                data = await handle.download_as_bytearray()          # v21+ API
            elif attempt == "download_as_bytearray":
                data = await handle.download_as_bytearray()
            elif attempt == "download_to_custom_path":
                await handle.download_to_custom_path(str(dest))
                return dest.stat().st_size
            else:
                await handle.download_to_drive(custom_path=str(dest))
                return dest.stat().st_size
            dest.write_bytes(data)
            return len(data)
        except Exception as exc:
            store.log_activity(f"download attempt '{attempt or 'download_as_bytearray'}' failed: {exc}")
    raise RuntimeError("Telegram file could not be downloaded with any known API")


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        store.log_activity(f"Blocked file from unknown chat {update.effective_chat.id}")
        return
    await update.message.reply_text("Downloading and reading that… 📄")
    config.ensure_dirs()
    doc = update.message.document
    dest = config.DOWNLOADS_DIR / (doc.file_name or doc.file_unique_id)
    try:
        if doc.file_size and doc.file_size > MAX_FILE_BYTES:
            await _reply(update, "That file is too big for me to handle — send it under 20MB please.")
            return
        await _download(doc, dest)
    except Exception as exc:
        store.log_activity(f"Agent download failed: {exc}")
        await _reply(update, "I couldn't download that file 😕 mind sending it again?")
        return

    import agent
    reply, _ = agent.handle_message(
        update.message.caption or f"(client uploaded {update.message.document.file_name})",
        attachment={"path": str(dest), "name": update.message.document.file_name},
    )
    await _reply(update, reply)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        store.log_activity(f"Blocked photo from unknown chat {update.effective_chat.id}")
        return
    largest = update.message.photo[-1]
    config.ensure_dirs()
    dest = config.DOWNLOADS_DIR / f"photo_{largest.file_unique_id}.jpg"
    try:
        await _download(largest, dest)
    except Exception as exc:
        store.log_activity(f"Agent photo download failed: {exc}")
        await _reply(update, "I couldn't download that photo 😕 mind resending?")
        return
    import agent
    reply, _ = agent.handle_message(
        update.message.caption or "(client sent a photo)", attachment={"path": str(dest), "name": dest.name}
    )
    await _reply(update, reply)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        store.log_activity(f"Blocked message from unknown chat {update.effective_chat.id}")
        return
    import agent
    reply, _ = agent.handle_message(update.message.text or "")
    await _reply(update, reply)


def _allowed_chat():
    """Configured client chat id, or None to accept anyone (fresh demo bot)."""
    try:
        return int(config.CLIENT_CHAT_ID) if config.CLIENT_CHAT_ID else None
    except ValueError:
        return None


def _is_allowed(update: Update) -> bool:
    """Blank CLIENT_CHAT_ID means 'accept any chat', not 'block everyone'."""
    allowed = _allowed_chat()
    return allowed is None or update.effective_chat.id == allowed


def build_app():
    if ApplicationBuilder is None:
        raise RuntimeError("python-telegram-bot is not installed. pip install -r requirements.txt")
    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(45)          # long-poll: keep each request under 50s
        .connection_pool_size(1)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    def quiet_error(update, context):
        """One line instead of a 60-line traceback when the network hiccups."""
        err = context.error
        print(f"   [telegram] transient error: {type(err).__name__}: {err}", flush=True)

    app.add_error_handler(quiet_error)
    return app


def run() -> None:
    import time
    config.ensure_dirs()
    print(f"   [telegram] bot starting, model={config.LLM_MODEL}")
    print(f"   [telegram] allowed chat: {config.CLIENT_CHAT_ID or 'any (first chat to message is used)'}")
    while True:
        try:
            build_app().run_polling(drop_pending_updates=False)
            break
        except KeyboardInterrupt:
            break
        except Exception as exc:
            # Network drops must never end the demo: reconnect and carry on.
            store.log_activity(f"Telegram connection dropped ({type(exc).__name__}), reconnecting in 5s")
            print(f"   [telegram] connection dropped ({type(exc).__name__}) - reconnecting in 5s", flush=True)
            time.sleep(5)
