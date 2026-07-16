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
        await q.answer("Отклонено")
        await _strip_and_note(q, "\n\n❌ Отклонено")
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
    await q.answer("Опубликовано ✅")
    await _strip_and_note(q, "\n\n✅ Опубликовано в группу")


async def _strip_and_note(q, note: str) -> None:
    """Убирает кнопки решения, дописывает статус к тексту/подписи."""
    try:
        if q.message.photo:
            await q.edit_message_caption(
                caption=(q.message.caption or "") + note, reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
        else:
            await q.edit_message_text(
                (q.message.text or "") + note, reply_markup=None,
                parse_mode=ParseMode.HTML, disable_web_page_preview=True,
            )
    except Exception:  # noqa: BLE001
        logger.debug("news: не удалось обновить сообщение админа", exc_info=True)


def build_news_handlers() -> list:
    return [CallbackQueryHandler(on_news_decision, pattern=r"^news:(pub|rej):\d+$")]
