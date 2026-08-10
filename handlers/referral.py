"""Реф-система: у каждого юзера — персональные одноразовые слоты-ссылки
`?start=ref_<referrer_id>_<slot>` (слот 1, 2, 3... — по одному на каждого
приглашённого). Новая ссылка выдаётся по команде /invite в личке или по
кнопке «🔗 Получить реф-ссылку» в панели группы (ui.group_menu_kb).

Привязка слота к конкретному человеку происходит в handlers/flow.py
(_consume_referral_payload при /start) — здесь только выдача ссылок и
статистики. «В ответе за приглашённого» — видимость связи в карточке
админа (handlers/admin_users.py), без автонаказаний.
"""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

import constants as C
from handlers.group_captcha import _mention, post_singleton_group_message

logger = logging.getLogger(__name__)


def _referral_link(bot_username: str, referrer_id: int, slot: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{referrer_id}_{slot}"


def _stats_line(context: ContextTypes.DEFAULT_TYPE, referrer_id: int) -> str:
    storage = context.bot_data["storage"]
    invited = storage.list_invited_by(referrer_id)
    if not invited:
        return "Пока никого не пригласили."
    banned = sum(1 for r in invited if storage.is_banned(r["invited_user_id"]))
    return f"Приглашено: {len(invited)} чел." + (f", из них забанено: {banned}" if banned else "")


async def cmd_invite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    storage = context.bot_data["storage"]
    slot = storage.create_referral_link(user.id)
    link = _referral_link(context.bot.username, user.id, slot)
    await update.message.reply_text(
        f"🔗 Ваша персональная ссылка (слот {slot}, одноразовая):\n"
        f"<code>{link}</code>\n\n"
        f"{_stats_line(context, user.id)}\n\n"
        "Каждый новый /invite выдаёт новую ссылку — старые остаются рабочими, "
        "пока ими не воспользовались.",
        parse_mode=ParseMode.HTML,
    )


async def _send_referral_link_and_confirm(context: ContextTypes.DEFAULT_TYPE, user, chat_id: int) -> None:
    """Общий сценарий для inline-кнопки, reply-кнопки и /invite из группы:
    ссылка уходит в личку, а в группе — подтверждение с кнопкой «Открыть бота»
    (один активный слот на чат, post_singleton_group_message, категория
    "referral_confirm" — новое подтверждение удаляет предыдущее)."""
    storage = context.bot_data["storage"]
    slot = storage.create_referral_link(user.id)
    link = _referral_link(context.bot.username, user.id, slot)
    dm_ok = True
    try:
        await context.bot.send_message(
            user.id,
            f"🔗 Ваша персональная ссылка (слот {slot}, одноразовая):\n"
            f"<code>{link}</code>\n\n"
            f"{_stats_line(context, user.id)}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:  # noqa: BLE001
        logger.debug("referral: не удалось отправить ссылку в личку %s", user.id, exc_info=True)
        dm_ok = False

    mention = _mention(user)
    text = (
        f"{mention}, ✅ ссылка отправлена вам в личные сообщения."
        if dm_ok else
        f"{mention}, не получилось написать вам в личку — откройте бота, "
        "нажмите Start и повторите."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
        "🤖 Открыть бота", url=f"https://t.me/{context.bot.username}",
    )]])
    try:
        await post_singleton_group_message(
            context, chat_id, "referral_confirm",
            lambda: context.bot.send_message(chat_id, text, reply_markup=kb, parse_mode=ParseMode.HTML),
        )
    except Exception:  # noqa: BLE001
        logger.debug("referral: не удалось отправить подтверждение в группу", exc_info=True)


async def cb_group_get_ref_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline-кнопка «Пригласить» в панели группы. answerCallbackQuery не умеет
    отдавать кнопки, поэтому подтверждение — отдельным сообщением, не алертом."""
    q = update.callback_query
    await q.answer()
    await _send_referral_link_and_confirm(context, q.from_user, q.message.chat.id)


async def on_group_invite_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Постоянная reply-клавиатура в группе (ui.group_reply_kb): нажатие шлёт
    ОБЫЧНОЕ текстовое сообщение с текстом кнопки — здесь оно перехватывается,
    стирается (Clean Chat, как /start) и обрабатывается тем же сценарием,
    что и inline-кнопка."""
    msg = update.effective_message
    try:
        await msg.delete()
    except Exception:  # noqa: BLE001
        logger.debug("referral: не удалось удалить сообщение-кнопку в группе", exc_info=True)
    await _send_referral_link_and_confirm(context, update.effective_user, update.effective_chat.id)


def build_referral_handlers() -> list:
    return [
        CommandHandler("invite", cmd_invite),
        CallbackQueryHandler(cb_group_get_ref_link, pattern=r"^ref_get_link$"),
    ]


def build_referral_group_handlers() -> list:
    """Отдельно от build_referral_handlers(): матчит ТОЧНЫЙ текст reply-кнопки
    в группах — оба варианта (RU/EN, см. ui.group_reply_kb). Регистрировать в
    bot.py ДО build_group_captcha() (тот же PTB group=1) — иначе широкий
    фильтр гейта (любое текстовое сообщение) в группе перехватит нажатие
    первым, и до этого хендлера очередь не дойдёт."""
    return [MessageHandler(
        filters.ChatType.GROUPS & filters.Text([C.GROUP_KB_INVITE_TEXT, C.GROUP_KB_INVITE_TEXT_EN]),
        on_group_invite_button,
    )]
