"""Гейт активности по подписке GURO ID для старых участников группы
(12.09.2026, ТЗ владельца: "написавший без подписки моментально мутится
до оплаты, сообщение сохраняется и публикуется обратно после оплаты").

Отдельно от гейта анкеты (group_captcha.py — "нет анкеты вообще"): этот
гейт применяется к тем, у кого анкета ЕСТЬ (has_profile), но нет активной
подписки GURO ID (guro_storage.any_subscription_active). Зарегистрирован
в СВОЕЙ PTB-группе (bot.py: group=2) — не group=1, где уже стоит гейт
анкеты с тем же широким фильтром: в пределах одной PTB-группы выигрывает
первый совпавший по ФИЛЬТРУ хендлер (внутренние return'ы функции на это
не влияют), так что в общем group=1 наш хендлер попросту не вызывался бы.

Реальных админов группы (не только settings.admin_ids) исключаем всегда —
владелец: "все кто в Community админ, могут спокойно писать без подписки".
"""
from __future__ import annotations

import logging

from telegram import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import ContextTypes, MessageHandler, filters

import constants as C
import logic
from handlers.group_captcha import _MUTED, _UNMUTED_FALLBACK, post_singleton_group_message

logger = logging.getLogger(__name__)


def _mention_html(user_id: int, display_name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{logic.html_escape(display_name)}</a>'


def _display_name(user) -> str:
    return getattr(user, "full_name", None) or getattr(user, "username", None) or "участник"


def _capture_content(msg) -> tuple[str, str | None, str | None]:
    """(kind, текст/подпись, file_id) — под то, что реально написал юзер.
    file_id остаётся валидным для повторной отправки без хранения самого
    файла — не нужен отдельный "сейф"-чат для сохранения медиа."""
    if msg.photo:
        return "photo", msg.caption, msg.photo[-1].file_id
    if msg.video:
        return "video", msg.caption, msg.video.file_id
    if msg.document:
        return "document", msg.caption, msg.document.file_id
    if msg.animation:
        return "animation", msg.caption, msg.animation.file_id
    if msg.voice:
        return "voice", msg.caption, msg.voice.file_id
    if msg.sticker:
        return "sticker", None, msg.sticker.file_id
    return "text", (msg.text or msg.caption or ""), None


async def _permissions_for_unmute(bot, chat_id: int) -> ChatPermissions:
    try:
        chat = await bot.get_chat(chat_id)
        if chat.permissions:
            return chat.permissions
    except Exception:  # noqa: BLE001
        logger.debug("sub_gate: get_chat permissions failed", exc_info=True)
    return _UNMUTED_FALLBACK


def _pay_kb(bot_username: str, label: str) -> InlineKeyboardMarkup:
    url = f"https://t.me/{bot_username}?start=pay_gate"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, url=url)]])


async def on_group_message_subscription_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.bot_data["settings"]
    if not settings.community_chat_id:
        return
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if msg is None or user is None or chat is None or getattr(user, "is_bot", False):
        return
    if getattr(msg, "sender_chat", None) is not None:
        return  # анонимные админы/каналы — не трогаем
    if chat.id != settings.community_chat_id:
        return
    if settings.is_admin(user.id):
        return
    if getattr(msg, "text", None) in (C.GROUP_KB_INVITE_TEXT, C.GROUP_KB_INVITE_TEXT_EN):
        return  # нажатие постоянной reply-кнопки "Пригласить/Invite" — не контент темы, не гейтим

    storage = context.bot_data["storage"]
    guro_storage = context.bot_data["guro_storage"]
    if not storage.has_profile(user.id):
        return  # это уже ловит гейт анкеты (group_captcha.on_group_message)
    if guro_storage.any_subscription_active(user.id):
        return

    cache = context.chat_data.setdefault("sub_gate_admin_cache", {})
    status = cache.get(user.id)
    if status is None:
        try:
            status = (await context.bot.get_chat_member(chat.id, user.id)).status
        except Exception:  # noqa: BLE001
            status = "?"
        cache[user.id] = status
    if status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        return

    kind, text, file_id = _capture_content(msg)
    thread_id = getattr(msg, "message_thread_id", None)
    display_name = _display_name(user)

    try:
        await context.bot.delete_message(chat.id, msg.message_id)
    except Exception:  # noqa: BLE001
        logger.warning(
            "sub_gate: не удалось удалить сообщение %s юзера %s в чате %s",
            msg.message_id, user.id, chat.id, exc_info=True,
        )

    try:
        await context.bot.restrict_chat_member(chat.id, user.id, permissions=_MUTED)
    except Exception:  # noqa: BLE001
        logger.warning("sub_gate: не удалось замутить %s в %s", user.id, chat.id, exc_info=True)

    guro_storage.save_gated_message(chat.id, user.id, thread_id, display_name, kind, text, file_id)
    logger.info(
        "sub_gate: сообщение юзера %s в чате %s (тема %s) отложено — нет активной подписки",
        user.id, chat.id, thread_id,
    )

    content = context.bot_data["content"]
    prompt_text = f"{_mention_html(user.id, display_name)}\n{content.txt('subscription_gate_group_prompt')}"
    kb = _pay_kb(context.bot.username, content.btn("pay_subscription"))
    await post_singleton_group_message(
        context, chat.id, f"sub_gate_{user.id}",
        lambda: context.bot.send_message(
            chat.id, prompt_text, message_thread_id=thread_id,
            reply_markup=kb, parse_mode=ParseMode.HTML,
        ),
    )


async def release_gated_message(bot, storage, guro_storage, chat_id: int, user_id: int) -> None:
    """Подписка оплачена — размутить и опубликовать отложенное сообщение
    (если было). Вызывается из handlers/guro_payments.py (Stars, в процессе
    бота) и guro_id_api.py:handle_crypto_webhook (крипта, отдельный процесс
    aiohttp с одноразовым Bot(...)) — поэтому принимает голый `bot`, а не
    PTB `context`."""
    try:
        perms = await _permissions_for_unmute(bot, chat_id)
        await bot.restrict_chat_member(chat_id, user_id, permissions=perms)
    except Exception:  # noqa: BLE001
        logger.debug("sub_gate: размут %s в %s не потребовался/не удался", user_id, chat_id, exc_info=True)

    prompt_id = storage.get_singleton_message(chat_id, f"sub_gate_{user_id}")
    if prompt_id:
        try:
            await bot.delete_message(chat_id, prompt_id)
        except Exception:  # noqa: BLE001
            logger.debug("sub_gate: не удалось удалить просьбу об оплате %s", prompt_id, exc_info=True)

    row = guro_storage.pop_gated_message(chat_id, user_id)
    if row is None:
        return

    thread_id = row["message_thread_id"]
    caption = _mention_html(user_id, row["display_name"])
    kind = row["kind"]

    if kind == "text":
        body = row["text"] or ""
        full_text = f"{caption}\n{body}" if body else caption
        await bot.send_message(chat_id, full_text, message_thread_id=thread_id, parse_mode=ParseMode.HTML)
        return

    if kind == "sticker":
        await bot.send_message(chat_id, caption, message_thread_id=thread_id, parse_mode=ParseMode.HTML)
        await bot.send_sticker(chat_id, row["file_id"], message_thread_id=thread_id)
        return

    sender = {
        "photo": bot.send_photo,
        "video": bot.send_video,
        "document": bot.send_document,
        "animation": bot.send_animation,
        "voice": bot.send_voice,
    }.get(kind)
    if sender is None:
        # неподдерживаемый тип (опрос/локация/контакт и т.п., редкий edge-case)
        # — восстановить содержимое нечем, хотя бы уведомляем, что писать снова можно
        await bot.send_message(chat_id, caption, message_thread_id=thread_id, parse_mode=ParseMode.HTML)
        return

    full_caption = f"{caption}\n{row['text']}" if row["text"] else caption
    await sender(chat_id, row["file_id"], caption=full_caption, message_thread_id=thread_id,
                 parse_mode=ParseMode.HTML)


def build_subscription_gate_handlers() -> list:
    return [MessageHandler(filters.ChatType.GROUPS & ~filters.StatusUpdate.ALL,
                            on_group_message_subscription_gate)]
