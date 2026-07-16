"""Гейт группы: доступ к чату только после анкеты (второй уровень бота).

Прошёл анкету (есть запись в profiles) — при входе сразу приветствие: видео
(CMS-медиа «captcha_welcome») + текст ENG/RU + инлайн-кнопки полезных ссылок.

Не прошёл — мут (restrict) + просьба пройти анкету с кнопкой на бота (текст
«gate_prompt» в CMS, просьба шлётся один раз на юзера). Списка участников у
Bot API нет, поэтому давние участники без анкеты ловятся по первому сообщению
(on_group_message); статусы админов группы кэшируются в chat_data. Мут
записывается в таблицу group_mutes; после завершения анкеты flow._finish
вызывает unmute_after_profile — бот размучивает и шлёт приветствие.

Капча отключена 15.07.2026; on_answer оставлен для старых сообщений капчи:
клик по ним удаляет сообщение. Тексты/видео/кнопки — в /admin (CMS).
"""
from __future__ import annotations

import asyncio
import logging

from telegram import (
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import constants as C
import logic
import ui

logger = logging.getLogger(__name__)

_FULL_MEMBER = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.OWNER,
    ChatMemberStatus.ADMINISTRATOR,
}

# Полный мут: запрещаем любые сообщения и медиа до прохождения капчи.
_MUTED = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)

# Запасной набор прав, если у чата не удалось прочитать дефолтные.
_UNMUTED_FALLBACK = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)


# --- helpers --------------------------------------------------------------

def _content(context):
    return context.bot_data["content"]


def _is_member(member) -> bool:
    status = member.status
    if status in _FULL_MEMBER:
        return True
    if status == ChatMemberStatus.RESTRICTED:
        return bool(member.is_member)
    return False


def _pending(context) -> dict:
    return context.chat_data.setdefault("captcha", {})


def gate_enabled(context) -> bool:
    """Тумблер гейта из /admin (дефолт — CAPTCHA_ENABLED из .env)."""
    settings = context.bot_data["settings"]
    return context.bot_data["storage"].get_flag("gate_enabled", settings.captcha_enabled)


def greeting_enabled(context) -> bool:
    """Тумблер приветствия новичкам из /admin (дефолт — вкл)."""
    return context.bot_data["storage"].get_flag("greeting_enabled", True)


def _mention(user) -> str:
    name = getattr(user, "full_name", None) or getattr(user, "username", None) or "новичок"
    return f'<a href="tg://user?id={user.id}">{logic.html_escape(name)}</a>'


def _options_kb(uid: int, options: list[int]) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(str(o), callback_data=f"cap:{uid}:{o}") for o in options
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


def _build_screen(context, user) -> tuple[str, InlineKeyboardMarkup, int]:
    """Готовит (текст, клавиатуру, верный_ответ) для нового примера."""
    content = _content(context)
    settings = context.bot_data["settings"]
    a, b = logic.make_captcha()
    answer = a + b
    options = logic.captcha_options(answer, settings.captcha_options)
    body = logic.render_captcha_text(content.txt("captcha_welcome"), a, b)
    text = f"{_mention(user)}\n{body}"
    return text, _options_kb(user.id, options), answer


async def _send_screen(context, chat_id: int, text: str, kb, key: str = "captcha_welcome"):
    """Отправляет экран: с медиа (CMS) — видео/гиф/фото+подпись, иначе текст."""
    media = _content(context).media(key)
    if media:
        file_id, mtype = media
        if mtype == "animation":
            return await context.bot.send_animation(
                chat_id, file_id, caption=text, reply_markup=kb, parse_mode=ParseMode.HTML
            )
        if mtype == "video":
            return await context.bot.send_video(
                chat_id, file_id, caption=text, reply_markup=kb, parse_mode=ParseMode.HTML
            )
        return await context.bot.send_photo(
            chat_id, file_id, caption=text, reply_markup=kb, parse_mode=ParseMode.HTML
        )
    return await context.bot.send_message(
        chat_id, text, reply_markup=kb, parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def _chat_permissions(context, chat_id: int) -> ChatPermissions:
    try:
        chat = await context.bot.get_chat(chat_id)
        if chat.permissions:
            return chat.permissions
    except Exception:  # noqa: BLE001
        logger.debug("captcha: get_chat permissions failed", exc_info=True)
    return _UNMUTED_FALLBACK


# --- handlers -------------------------------------------------------------

async def on_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вступление: приветствие, если анкета пройдена, иначе мут до анкеты."""
    settings = context.bot_data["settings"]
    if not settings.captcha_enabled:
        return
    cmu = update.chat_member
    if cmu is None:
        return
    chat = cmu.chat
    if settings.captcha_group_ids and chat.id not in settings.captcha_group_ids:
        return
    was = _is_member(cmu.old_chat_member)
    now = _is_member(cmu.new_chat_member)
    if was or not now:
        return  # не вступление (правки статуса, выход и т.п.)
    user = cmu.new_chat_member.user
    if getattr(user, "is_bot", False):
        return

    storage = context.bot_data["storage"]
    if storage.has_profile(user.id) or settings.is_admin(user.id) or not gate_enabled(context):
        if greeting_enabled(context):
            await _send_greeting(context, chat.id, user)
        return
    await _gate_mute(context, chat.id, user)


async def on_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Нажатие варианта ответа под капчей."""
    q = update.callback_query
    try:
        _, uid_s, val_s = q.data.split(":")
        uid, val = int(uid_s), int(val_s)
    except (ValueError, AttributeError):
        await q.answer()
        return

    if q.from_user.id != uid:
        await q.answer("Это не ваша капча 🙂", show_alert=True)
        return

    pending = _pending(context)
    info = pending.get(uid)
    if not info:
        # состояние потеряно (рестарт без pending) — снимаем капчу, не мучаем
        await q.answer()
        await _safe_delete(q)
        return

    is_media = bool(q.message.video or q.message.animation or q.message.photo)

    if val == info["answer"]:
        await q.answer("Готово ✅")
        chat_id = q.message.chat_id
        perms = await _chat_permissions(context, chat_id)
        try:
            await context.bot.restrict_chat_member(chat_id, uid, permissions=perms)
        except Exception:  # noqa: BLE001
            logger.exception("captcha: не удалось размутить %s", uid)
        pending.pop(uid, None)
        await _edit_to_success(context, q, is_media)
        return

    # неверно — новый пример в том же сообщении, остаётся в муте
    await q.answer("Неверно, попробуйте ещё раз")
    text, kb, answer = _build_screen(context, q.from_user)
    info["answer"] = answer
    try:
        if is_media:
            await q.edit_message_caption(
                caption=text, reply_markup=kb, parse_mode=ParseMode.HTML
            )
        else:
            await q.edit_message_text(
                text, reply_markup=kb, parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
    except Exception:  # noqa: BLE001
        logger.debug("captcha: не удалось обновить пример", exc_info=True)


async def _edit_to_success(context, q, is_media: bool) -> None:
    """Верный ответ: редактируем ТО ЖЕ сообщение — убираем капчу, ставим 5 кнопок-ссылок."""
    content = _content(context)
    text = f"{_mention(q.from_user)}\n{content.txt('captcha_success')}"
    kb = ui.group_menu_kb(context.bot_data["storage"])
    try:
        if is_media:
            await q.edit_message_caption(
                caption=text, reply_markup=kb, parse_mode=ParseMode.HTML
            )
        else:
            await q.edit_message_text(
                text, reply_markup=kb, parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
    except Exception:  # noqa: BLE001
        logger.exception("captcha: не удалось отредактировать сообщение после успеха")


async def _safe_delete(q) -> None:
    try:
        await q.message.delete()
    except Exception:  # noqa: BLE001
        pass


async def _send_greeting(context, chat_id: int, user) -> None:
    """Приветствие прошедшему анкету: CMS-медиа + текст + панель ссылок."""
    text = f"{_mention(user)}\n{_content(context).txt('captcha_welcome')}"
    kb = ui.group_menu_kb(context.bot_data["storage"])
    await _send_screen(context, chat_id, text, kb)
    logger.info("welcome: greeting sent to user %s in chat %s", user.id, chat_id)


def _gate_kb(context) -> InlineKeyboardMarkup:
    # deep-link: по кнопке Telegram показывает Start, бот получает /start gate
    # и удаляет эту просьбу в группе (delete_gate_prompts из flow.start).
    label = _content(context).btn("gate")
    url = f"https://t.me/{context.bot.username}?start=gate"
    return InlineKeyboardMarkup([[ui.link_button(label, url, emoji_id=C.GATE_BUTTON_EMOJI_ID)]])


async def _gate_mute(context, chat_id: int, user) -> None:
    """Мутит участника без анкеты; просьбу пройти анкету шлёт один раз на юзера."""
    try:
        await context.bot.restrict_chat_member(chat_id, user.id, permissions=_MUTED)
    except Exception:  # noqa: BLE001
        logger.warning("gate: не удалось замутить %s в %s", user.id, chat_id, exc_info=True)
        return
    context.bot_data["storage"].add_group_mute(chat_id, user.id)
    logger.info("gate: muted user %s in chat %s (no profile)", user.id, chat_id)

    prompted = context.chat_data.setdefault("gate_prompted", [])
    if user.id in prompted:
        return
    prompted.append(user.id)
    text = f"{_mention(user)}\n{_content(context).txt('gate_prompt')}"
    try:
        msg = await _send_screen(context, chat_id, text, _gate_kb(context), key="gate_prompt")
    except Exception:  # noqa: BLE001
        logger.warning("gate: просьба для %s в %s не отправлена", user.id, chat_id, exc_info=True)
        return
    context.bot_data["storage"].set_gate_prompt(chat_id, user.id, msg.message_id)


async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ленивый гейт для давних участников: сообщение от юзера без анкеты → мут.

    Bot API не отдаёт список участников, поэтому существующие 5к+ ловятся по
    первому сообщению. Статус админов группы кэшируется в chat_data.
    """
    settings = context.bot_data["settings"]
    if not gate_enabled(context):
        return
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if msg is None or user is None or chat is None or getattr(user, "is_bot", False):
        return
    if getattr(msg, "sender_chat", None) is not None:
        return  # анонимные админы и каналы — не трогаем
    if settings.captcha_group_ids and chat.id not in settings.captcha_group_ids:
        return
    if settings.is_admin(user.id):
        return
    if context.bot_data["storage"].has_profile(user.id):
        return
    cache = context.chat_data.setdefault("gate_admin_cache", {})
    status = cache.get(user.id)
    if status is None:
        try:
            status = (await context.bot.get_chat_member(chat.id, user.id)).status
        except Exception:  # noqa: BLE001
            status = "?"
        cache[user.id] = status
    if status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        return
    await _gate_mute(context, chat.id, user)


async def delete_gate_prompts(context, user_id: int) -> None:
    """Юзер пришёл в бота — подчищаем в группах просьбы «пройди анкету»."""
    storage = context.bot_data["storage"]
    for chat_id, msg_id in storage.pop_gate_prompts(user_id):
        try:
            await context.bot.delete_message(chat_id, msg_id)
            logger.info("gate: prompt %s deleted in chat %s", msg_id, chat_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "gate: не удалось удалить просьбу %s в %s", msg_id, chat_id, exc_info=True
            )


async def gate_unmute_all(context) -> int:
    """Гейт выключили: размучиваем всех из group_mutes, подчищаем просьбы."""
    storage = context.bot_data["storage"]
    rows = storage.all_group_mutes()
    perms_cache: dict = {}
    done = 0
    for chat_id, user_id, prompt_msg_id in rows:
        try:
            if chat_id not in perms_cache:
                perms_cache[chat_id] = await _chat_permissions(context, chat_id)
            await context.bot.restrict_chat_member(
                chat_id, user_id, permissions=perms_cache[chat_id]
            )
            done += 1
        except Exception:  # noqa: BLE001
            logger.warning("gate: размут %s в %s не удался", user_id, chat_id, exc_info=True)
        if prompt_msg_id:
            try:
                await context.bot.delete_message(chat_id, prompt_msg_id)
            except Exception:  # noqa: BLE001
                logger.debug("gate: просьба %s не удалена", prompt_msg_id, exc_info=True)
        await asyncio.sleep(0.05)
    storage.clear_group_mutes()
    logger.info("gate: тумблер выключен, размучено %s из %s", done, len(rows))
    return done


async def unmute_after_profile(context, user) -> None:
    """Анкета пройдена: размут во всех группах, где гейт мутил, + приветствие."""
    await delete_gate_prompts(context, user.id)  # подстраховка, если /start не удалил
    storage = context.bot_data["storage"]
    for chat_id in storage.pop_group_mutes(user.id):
        try:
            perms = await _chat_permissions(context, chat_id)
            await context.bot.restrict_chat_member(chat_id, user.id, permissions=perms)
        except Exception:  # noqa: BLE001
            logger.exception("gate: не удалось размутить %s в %s", user.id, chat_id)
            continue
        logger.info("gate: unmuted user %s in chat %s (profile done)", user.id, chat_id)
        try:
            await _send_greeting(context, chat_id, user)
        except Exception:  # noqa: BLE001
            logger.warning("gate: приветствие после размута не отправлено", exc_info=True)


def build_group_captcha() -> list:
    return [
        ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER),
        CallbackQueryHandler(on_answer, pattern=r"^cap:\d+:\d+$"),
        MessageHandler(filters.ChatType.GROUPS & ~filters.StatusUpdate.ALL, on_group_message),
    ]
