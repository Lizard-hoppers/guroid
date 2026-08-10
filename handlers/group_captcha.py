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


async def _send_screen(context, chat_id: int, text: str, kb, key: str = "captcha_welcome",
                        message_thread_id: int | None = None, media_override=None,
                        reply_to_message_id: int | None = None):
    """Отправляет экран: с медиа (CMS) — видео/гиф/фото+подпись, иначе текст.

    message_thread_id — топик форума (EN-приветствие уходит в свою тему,
    см. _send_greeting; гейт-промпт — топик, где юзер написал), None — топик
    по умолчанию (текущее поведение).
    media_override — (file_id, media_type) в обход CMS-медиа по key (см.
    _send_greeting: ротация из пула greeting_videos вместо статичного видео).
    reply_to_message_id — ответом на сообщение юзера (гейт-промпт под ним),
    allow_sending_without_reply — если то сообщение уже удалено, шлём как
    обычное, а не роняем гейт с ошибкой."""
    media = media_override if media_override is not None else _content(context).media(key)
    if media:
        file_id, mtype = media
        if mtype == "animation":
            return await context.bot.send_animation(
                chat_id, file_id, caption=text, reply_markup=kb, parse_mode=ParseMode.HTML,
                message_thread_id=message_thread_id, reply_to_message_id=reply_to_message_id,
                allow_sending_without_reply=True,
            )
        if mtype == "video":
            return await context.bot.send_video(
                chat_id, file_id, caption=text, reply_markup=kb, parse_mode=ParseMode.HTML,
                message_thread_id=message_thread_id, reply_to_message_id=reply_to_message_id,
                allow_sending_without_reply=True,
            )
        return await context.bot.send_photo(
            chat_id, file_id, caption=text, reply_markup=kb, parse_mode=ParseMode.HTML,
            message_thread_id=message_thread_id, reply_to_message_id=reply_to_message_id,
            allow_sending_without_reply=True,
        )
    return await context.bot.send_message(
        chat_id, text, reply_markup=kb, parse_mode=ParseMode.HTML,
        disable_web_page_preview=True, message_thread_id=message_thread_id,
        reply_to_message_id=reply_to_message_id, allow_sending_without_reply=True,
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


async def post_singleton_group_message(context, chat_id: int, category: str, sender) -> None:
    """Clean Chat в группе: один активный слот на (chat_id, category) — новое
    сообщение этой категории удаляет предыдущее вместо накопления в чате.
    Слот хранится в БД (Storage.get/set_singleton_message), переживает
    рестарт бота — в отличие от прежнего TTL-таймера."""
    storage = context.bot_data["storage"]
    old_id = storage.get_singleton_message(chat_id, category)
    if old_id:
        try:
            await context.bot.delete_message(chat_id, old_id)
        except Exception:  # noqa: BLE001
            logger.debug(
                "singleton: не удалось удалить старое сообщение %s/%s", chat_id, category, exc_info=True
            )
    msg = await sender()
    if msg is not None:
        storage.set_singleton_message(chat_id, category, msg.message_id)


def spawn_background(context, coro) -> None:
    """Настоящий fire-and-forget: НЕ через context.application.create_task —
    PTB явно AWAIT-ит все такие задачи при Application.stop() (см. исходник
    _application.py: `await asyncio.gather(*self.__create_task_tasks)`), а
    значит часовой asyncio.sleep вешает КАЖДЫЙ рестарт/деплой бота на 90 сек
    до принудительного SIGKILL от systemd (так и было обнаружено 20.07.2026 —
    админка «зависала» из-за этого). Используем голый asyncio.create_task и
    сами держим ссылку в bot_data, чтобы GC не прибил задачу раньше времени."""
    task = asyncio.create_task(coro)
    tasks = context.bot_data.setdefault("_bg_tasks", set())
    tasks.add(task)
    task.add_done_callback(tasks.discard)


async def _send_greeting(context, chat_id: int, user) -> None:
    """Приветствие прошедшему анкету: CMS-медиа + текст + панель ссылок.

    Локализовано по языку анкеты (profiles.lang, 24.07.2026): RU уходит в
    основной топик чата, EN — в COMMUNITY_EN_TOPIC_ID (свой англоязычный
    топик того же форума). Профиля/lang нет (старые анкеты) — фолбэк на ru.

    Свой singleton-слот НА ТОПИК (суффикс категории) — иначе RU- и
    EN-приветствия делили бы один слот на chat_id и удаляли бы друг друга
    при каждом новом участнике, хотя физически лежат в разных темах."""
    storage = context.bot_data["storage"]
    profile = storage.get_profile_by_telegram_id(user.id)
    lang = profile["lang"] if profile and profile["lang"] else "ru"
    settings = context.bot_data["settings"]
    thread_id = settings.community_en_topic_id if lang == "en" else None
    cat_suffix = f"_{thread_id}" if thread_id else ""

    text = f"{_mention(user)}\n{_content(context).view(lang).txt('group_greeting')}"
    kb = ui.group_menu_kb(storage, lang=lang)
    # Разнообразие (24.07.2026): видео по кругу из пула greeting_videos вместо
    # одного статичного CMS-медиа; пул пуст -> _send_screen сам упадёт на
    # обычный CMS-лукап по key="captcha_welcome" (текущее поведение).
    video = storage.greeting_video_next()
    await post_singleton_group_message(
        context, chat_id, f"greeting{cat_suffix}",
        lambda: _send_screen(context, chat_id, text, kb, message_thread_id=thread_id, media_override=video),
    )
    logger.info("welcome: greeting sent to user %s in chat %s (lang=%s)", user.id, chat_id, lang)

    # Reply-клавиатура (ui.group_reply_kb) — отдельным сообщением, т.к. Telegram
    # не даёт совместить inline- и reply-разметку в одном; переустанавливается
    # при каждом новом участнике, чтобы дошла и до тех, кто вступил позже.
    invite_label = C.GROUP_KB_INVITE_TEXT_EN if lang == "en" else C.GROUP_KB_INVITE_TEXT
    hint = (
        f"👋 Want to invite a friend? Tap «{invite_label}» below."
        if lang == "en" else
        f"👋 Хотите пригласить друга? Жмите «{invite_label}» внизу."
    )
    await post_singleton_group_message(
        context, chat_id, f"invite_keyboard{cat_suffix}",
        lambda: context.bot.send_message(
            chat_id, hint, reply_markup=ui.group_reply_kb(lang=lang), message_thread_id=thread_id,
        ),
    )


def _gate_kb(context) -> InlineKeyboardMarkup:
    # deep-link: по кнопке Telegram показывает Start, бот получает /start gate
    # и удаляет эту просьбу в группе (delete_gate_prompts из flow.start).
    label = _content(context).btn("gate")
    url = f"https://t.me/{context.bot.username}?start=gate"
    return InlineKeyboardMarkup([[ui.link_button(label, url, emoji_id=C.GATE_BUTTON_EMOJI_ID)]])


GATE_PROMPT_TTL_SECONDS = 1800  # 30 минут — не увидел юзер, просьба сама уберётся


async def _expire_gate_prompt(context, chat_id: int, user_id: int, message_id: int,
                               delay: int = GATE_PROMPT_TTL_SECONDS) -> None:
    """Через delay секунд удаляет просьбу, ЕСЛИ это ещё тот же промпт (не был
    уже снят через /start — delete_gate_prompts) — иначе ничего не делает.
    delay параметризован ради тестов (реальный вызов всегда с дефолтом)."""
    await asyncio.sleep(delay)
    storage = context.bot_data["storage"]
    if storage.get_gate_prompt(chat_id, user_id) != message_id:
        return
    try:
        await context.bot.delete_message(chat_id, message_id)
        logger.info("gate: prompt %s истёк по таймауту в чате %s", message_id, chat_id)
    except Exception:  # noqa: BLE001
        logger.debug("gate: не удалось удалить просроченную просьбу %s в %s", message_id, chat_id, exc_info=True)
    storage.clear_gate_prompt(chat_id, user_id)


async def _gate_mute(context, chat_id: int, user, message_thread_id: int | None = None,
                      reply_to_message_id: int | None = None) -> None:
    """Мутит участника без анкеты; просьбу пройти анкету шлёт один раз на юзера
    — в ТОЙ теме форума, где он написал, ответом под его сообщением (если это
    вход в группу, а не сообщение — message_thread_id/reply_to_message_id нет,
    просьба уходит в топик по умолчанию, как раньше).

    Забаненного администратором (storage.is_banned) НЕ трогаем через обычный
    гейт-мут: не пишем в group_mutes (иначе заполнение анкеты автоматически
    снимет бан через unmute_after_profile) и не шлём бесполезную для него
    просьбу пройти анкету — ограничение и так уже действует."""
    if context.bot_data["storage"].is_banned(user.id):
        try:
            await context.bot.restrict_chat_member(chat_id, user.id, permissions=_MUTED)
        except Exception:  # noqa: BLE001
            logger.warning("gate: не удалось замутить забаненного %s в %s", user.id, chat_id, exc_info=True)
        return
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
        msg = await _send_screen(
            context, chat_id, text, _gate_kb(context), key="gate_prompt",
            message_thread_id=message_thread_id, reply_to_message_id=reply_to_message_id,
        )
    except Exception:  # noqa: BLE001
        logger.warning("gate: просьба для %s в %s не отправлена", user.id, chat_id, exc_info=True)
        return
    context.bot_data["storage"].set_gate_prompt(chat_id, user.id, msg.message_id)
    spawn_background(context, _expire_gate_prompt(context, chat_id, user.id, msg.message_id))


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
    await _gate_mute(
        context, chat.id, user,
        message_thread_id=getattr(msg, "message_thread_id", None),
        reply_to_message_id=msg.message_id,
    )


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
