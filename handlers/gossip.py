"""Сплетни/инсайды от участников: только прошедшие анкету, текстом в личку
боту (/gossip) -> GPT-оформление (gossip_formatter.py) -> черновик всем
админам с ✅/❌ -> публикация в тот же чат, что и новости (NEWS_CHAT_ID).

В отличие от news_poster.py (отдельный процесс, периодический опрос RSS),
здесь GPT-вызов происходит прямо в хендлере — это прямой ответ на действие
живого пользователя, а не фоновая задача, откладывать его в отдельный
процесс незачем.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from gossip_formatter import format_with_gpt, render_raw_fallback, render_telegram_html

logger = logging.getLogger(__name__)

WAIT_TEXT = 0

MIN_LEN = 15
MAX_LEN = 1500
COOLDOWN = timedelta(hours=24)


def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = context.bot_data["settings"]
    user = update.effective_user
    return bool(user and settings.is_admin(user.id))


async def _delete_user_msg(update: Update) -> None:
    try:
        await update.message.delete()
    except Exception:  # noqa: BLE001
        pass


def _within_cooldown(last_iso: str) -> bool:
    try:
        last = datetime.strptime(last_iso, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - last < COOLDOWN


async def gossip_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _delete_user_msg(update)
    chat_id = update.effective_chat.id
    user = update.effective_user
    storage = context.bot_data["storage"]
    settings = context.bot_data["settings"]

    if update.effective_chat.type != "private":
        await context.bot.send_message(
            chat_id, "Напишите боту в личку /gossip — это не для группового чата.",
        )
        return ConversationHandler.END

    if not storage.has_profile(user.id) and not settings.is_admin(user.id):
        await context.bot.send_message(
            chat_id,
            "Эта функция доступна только участникам, прошедшим анкету. "
            "Отправьте /start, чтобы пройти её.",
        )
        return ConversationHandler.END

    if not storage.get_flag("gossip_enabled", True):
        await context.bot.send_message(chat_id, "Приём сплетен сейчас временно отключён.")
        return ConversationHandler.END

    last = storage.gossip_last_submission_at(user.id)
    if last and _within_cooldown(last):
        await context.bot.send_message(
            chat_id, "Вы уже присылали сплетню сегодня — попробуйте завтра 🙂",
        )
        return ConversationHandler.END

    await context.bot.send_message(
        chat_id,
        "\U0001f5e3 Расскажите, что слышали — коротко, без имён и оскорблений, "
        "если можно. Мы оформим это в анонимную заметку и отправим на модерацию.\n\n"
        "Для отмены — /cancel.",
    )
    return WAIT_TEXT


async def gossip_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _delete_user_msg(update)
    await context.bot.send_message(
        update.effective_chat.id, "Пришлите, пожалуйста, текстом.",
    )
    return WAIT_TEXT


async def gossip_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id
    await _delete_user_msg(update)

    if len(text) < MIN_LEN:
        await context.bot.send_message(
            chat_id,
            f"Слишком коротко, напишите чуть подробнее (от {MIN_LEN} символов) "
            "или /cancel.",
        )
        return WAIT_TEXT
    text = text[:MAX_LEN]

    user = update.effective_user
    settings = context.bot_data["settings"]
    storage = context.bot_data["storage"]

    status_msg = await context.bot.send_message(chat_id, "⏳ Обрабатываю...")

    fg = None
    if settings.openai_api_key:
        fg = await format_with_gpt(settings.openai_api_key, settings.openai_model, text)
    if fg is not None:
        rendered = render_telegram_html(fg)
        flagged = fg.flagged
    else:
        rendered = render_raw_fallback(text)
        flagged = False

    draft_id = storage.gossip_save_draft(
        user.id, user.username or "", text, rendered, flagged=flagged,
    )
    await _notify_admins(context, settings, storage, draft_id, rendered, flagged)

    try:
        await status_msg.delete()
    except Exception:  # noqa: BLE001
        pass
    await context.bot.send_message(chat_id, "Спасибо! Ваша сплетня отправлена на модерацию \U0001f64c")
    return ConversationHandler.END


async def gossip_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _delete_user_msg(update)
    await context.bot.send_message(update.effective_chat.id, "Отменено.")
    return ConversationHandler.END


def _draft_kb(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Опубликовать", callback_data=f"gossip:pub:{draft_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"gossip:rej:{draft_id}"),
    ]])


async def _notify_admins(context, settings, storage, draft_id: int, text: str,
                          flagged: bool) -> None:
    prefix = "⚠️ <b>Возможен риск, проверьте перед публикацией</b>\n\n" if flagged else ""
    admin_text = prefix + text
    admin_chat_id = admin_msg_id = None
    for aid in settings.admin_ids:
        try:
            msg = await context.bot.send_message(
                aid, admin_text, parse_mode=ParseMode.HTML,
                disable_web_page_preview=True, reply_markup=_draft_kb(draft_id),
            )
            admin_chat_id, admin_msg_id = aid, msg.message_id
        except Exception:  # noqa: BLE001
            logger.exception("gossip: не удалось уведомить админа %s", aid)
    if admin_msg_id:
        storage.gossip_set_admin_msg(draft_id, admin_chat_id, admin_msg_id)


async def on_gossip_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not _is_admin(update, context):
        await q.answer("Только для админов", show_alert=True)
        return

    _, action, id_s = q.data.split(":")
    draft_id = int(id_s)
    storage = context.bot_data["storage"]
    draft = storage.gossip_get_draft(draft_id)
    if draft is None:
        await q.answer("Черновик не найден", show_alert=True)
        return
    if draft["status"] != "pending":
        await q.answer("Уже обработано другим админом", show_alert=True)
        return

    settings = context.bot_data["settings"]

    if action == "rej":
        storage.gossip_set_status(draft_id, "rejected")
        storage.log_action(update.effective_user.id, "gossip_reject", f"черновик #{draft_id}")
        await q.answer("Отклонено")
        await _strip_and_note(q, "\n\n❌ Отклонено")
        return

    if not settings.news_chat_id:
        await q.answer("NEWS_CHAT_ID не настроен в .env", show_alert=True)
        return
    try:
        kwargs = {}
        if settings.gossip_topic_id:
            kwargs["message_thread_id"] = settings.gossip_topic_id
        await context.bot.send_message(
            settings.news_chat_id, draft["text"], parse_mode=ParseMode.HTML,
            disable_web_page_preview=True, **kwargs,
        )
    except Exception:  # noqa: BLE001
        logger.exception("gossip: публикация черновика %s не удалась", draft_id)
        await q.answer("Ошибка публикации, смотри логи", show_alert=True)
        return

    storage.gossip_set_status(draft_id, "published", published=True)
    storage.log_action(update.effective_user.id, "gossip_publish", f"черновик #{draft_id}")
    await q.answer("Опубликовано ✅")
    await _strip_and_note(q, "\n\n✅ Опубликовано в группу")


async def _strip_and_note(q, note: str) -> None:
    try:
        await q.edit_message_text(
            (q.message.text or "") + note, reply_markup=None,
            parse_mode=ParseMode.HTML, disable_web_page_preview=True,
        )
    except Exception:  # noqa: BLE001
        logger.debug("gossip: не удалось обновить сообщение админа", exc_info=True)


def build_gossip_handlers() -> list:
    conv = ConversationHandler(
        entry_points=[CommandHandler("gossip", gossip_start)],
        states={
            WAIT_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, gossip_text),
                MessageHandler(~filters.COMMAND, gossip_non_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", gossip_cancel)],
        allow_reentry=True,
        name="gambling_gossip",
        persistent=True,
    )
    return [conv, CallbackQueryHandler(on_gossip_decision, pattern=r"^gossip:(pub|rej):\d+$")]
