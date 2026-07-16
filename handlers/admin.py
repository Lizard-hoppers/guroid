"""Админ-команды: /export (CSV всех анкет), /stats (счётчик)."""
from __future__ import annotations

import io

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes


def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = context.bot_data["settings"]
    user = update.effective_user
    return bool(user and settings.is_admin(user.id))


async def _del_cmd(update: Update) -> None:
    """Clean Chat: убираем сообщение-команду пользователя."""
    try:
        await update.message.delete()
    except Exception:  # noqa: BLE001
        pass


async def export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await _del_cmd(update)
    if not _is_admin(update, context):
        return
    storage = context.bot_data["storage"]
    csv_text = storage.export_csv()
    data = io.BytesIO(csv_text.encode("utf-8-sig"))
    data.name = "gambling_profiles.csv"
    await context.bot.send_document(
        chat_id,
        document=data,
        filename="gambling_profiles.csv",
        caption=f"Всего анкет: {storage.count()}",
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    await _del_cmd(update)
    await context.bot.send_message(
        chat_id,
        f"Ваш Telegram ID: <code>{uid}</code>\n"
        "Передайте его администратору бота, чтобы добавить в ADMIN_IDS.",
        parse_mode="HTML",
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await _del_cmd(update)
    if not _is_admin(update, context):
        return
    storage = context.bot_data["storage"]
    sheet = context.bot_data["sheet"]
    unsynced = len(storage.unsynced())
    await context.bot.send_message(
        chat_id,
        f"Анкет всего: {storage.count()}\n"
        f"Google Sheets: {'включён' if sheet.enabled else 'выключен (заглушка)'}\n"
        f"Не синхронизировано в таблицу: {unsynced}",
    )


def build_admin_handlers() -> list:
    return [
        CommandHandler("myid", myid),
        CommandHandler("export", export),
        CommandHandler("stats", stats),
    ]
