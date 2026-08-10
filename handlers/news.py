"""Публикация/отклонение новостных черновиков — кнопки шлёт news_poster.py
(отдельный процесс), а обрабатывает их основной бот (тут), т.к. только он
слушает getUpdates. draft_id прилетает в callback_data, весь черновик — из БД,
поэтому обработчик не завязан на то, какой конкретно процесс создал черновик.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, ContextTypes

from news_formatter import send_news_html

logger = logging.getLogger(__name__)


def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = context.bot_data["settings"]
    return settings.is_admin(update.effective_user.id)


async def on_news_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not _is_admin(update, context):
        await q.answer("Только для админов", show_alert=True)
        return

    _, action, id_s = q.data.split(":")
    draft_id = int(id_s)
    storage = context.bot_data["storage"]
    draft = storage.news_get_draft(draft_id)
    if draft is None:
        await q.answer("Черновик не найден", show_alert=True)
        return
    if draft["status"] != "pending":
        await q.answer("Уже обработано другим админом", show_alert=True)
        return

    settings = context.bot_data["settings"]

    if action == "rej":
        storage.news_set_status(draft_id, "rejected")
        storage.log_action(update.effective_user.id, "news_reject", f"черновик #{draft_id}")
        await q.answer("Отклонено")
        await _delete_admin_copies(context, storage, draft_id)
        return

    # action == "pub"
    if not settings.news_chat_id:
        await q.answer("NEWS_CHAT_ID не настроен в .env", show_alert=True)
        return
    try:
        kwargs = {}
        if settings.news_topic_id:
            kwargs["message_thread_id"] = settings.news_topic_id
        await send_news_html(
            context.bot, settings.news_chat_id, draft["text"], draft["image_url"],
            ParseMode.HTML, **kwargs,
        )
    except Exception:  # noqa: BLE001
        logger.exception("news: публикация черновика %s не удалась", draft_id)
        await q.answer("Ошибка публикации, смотри логи", show_alert=True)
        return

    storage.news_set_status(draft_id, "published", published=True)
    storage.log_action(update.effective_user.id, "news_publish", f"черновик #{draft_id}")
    await q.answer("Опубликовано ✅")
    await _delete_admin_copies(context, storage, draft_id)


async def _delete_admin_copies(context: ContextTypes.DEFAULT_TYPE, storage, draft_id: int) -> None:
    """Убирает копию черновика у ВСЕХ админов, не только у того, кто нажал
    кнопку — news_admin_messages хранит ID сообщения у каждого отдельно."""
    for row in storage.news_list_admin_msgs(draft_id):
        try:
            await context.bot.delete_message(row["admin_chat_id"], row["admin_msg_id"])
        except Exception:  # noqa: BLE001
            logger.debug(
                "news: не удалось удалить копию черновика %s у админа %s",
                draft_id, row["admin_chat_id"], exc_info=True,
            )
    storage.news_clear_admin_msgs(draft_id)


def build_news_handlers() -> list:
    return [CallbackQueryHandler(on_news_decision, pattern=r"^news:(pub|rej):\d+$")]
