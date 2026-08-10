"""Раздел /admin «Пользователи»: список всех известных системе участников
(по анкетам) с кликабельным Telegram ID + поиск по ID/@username, карточка с
реальными модераторскими действиями в группе сообщества (мут на время /
бан-ограничение навсегда / разбан) — по образцу island_summary_bot
(user_cards.py/ui.py — кликабельный ID через deep-link `?start=u_<id>`).

В отличие от «Анкет» (карточка — деловые данные заявки), карточка тут — про
модерацию конкретного Telegram-юзера: можно найти и замодерировать ЛЮБОГО
участника группы по ID, даже без анкеты — Bot API не отдаёт список участников
супергруппы, поэтому список опирается на тех, кто заполнил анкету (это и есть
наш реестр «известных» пользователей), а точечный поиск по ID работает для
кого угодно (то же ограничение, что и у гейта в group_captcha.py).

«Бан» реализован как перманентный restrict_chat_member (без until_date) —
человек остаётся в группе, но не может писать; это обратимо через «Разбанить»,
в отличие от настоящего kick/ban_chat_member. Тот же выбор сделан в
island_summary_bot (см. admin:ban_execute там).

Модераторские кнопки карточки (мут/бан/разбан) и быстрый лукап по форварду —
ВНЕ ConversationHandler-состояний (build_admin_users_handlers, group=1 в
bot.py): карточка может открыться первым сообщением для админа, который ещё
ни разу не заходил в /admin (по форварду или по deep-link из списка), и тогда
у него нет активного состояния conversation — кнопки внутри states работать
бы не стали. Список/пагинация/поиск остаются в ConversationHandler — это
часть обычной навигации /admin.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

import logic
from handlers import admin_ui
from handlers.admin_ui import BROWSE
from handlers.group_captcha import _MUTED, _chat_permissions

WAIT_LOOKUP = "usr:lookup"
PAGE_SIZE = 20

MUTE_OPTIONS: tuple[tuple[str, timedelta], ...] = (
    ("10 мин", timedelta(minutes=10)),
    ("1 час", timedelta(hours=1)),
    ("24 часа", timedelta(hours=24)),
)

_STATUS_LABELS = {
    ChatMemberStatus.OWNER: "👑 Владелец группы",
    ChatMemberStatus.ADMINISTRATOR: "🛡 Админ группы",
    ChatMemberStatus.MEMBER: "🟢 Участник",
    ChatMemberStatus.RESTRICTED: "🔇 Ограничен (мут/бан)",
    ChatMemberStatus.LEFT: "⬅️ Не в группе",
    ChatMemberStatus.BANNED: "⛔ Кикнут из группы",
}


def user_card_start_url(bot_username: str, user_id: int) -> str:
    """Deep-link, по клику на который бот сразу открывает карточку участника."""
    return f"https://t.me/{bot_username}?start=u_{user_id}"


# --- список известных пользователей (по анкетам), с пагинацией -----------

def _users_list_kb(page: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("← Назад", callback_data=f"acms_users_p:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("Вперёд →", callback_data=f"acms_users_p:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("‹ Панель управления", callback_data="acms_home")])
    return InlineKeyboardMarkup(rows)


def _users_list_line(r, index: int, bot_username: str | None) -> str:
    uid = r["user_id"]
    uname = f"@{logic.html_escape(r['username'])}" if r["username"] else "—"
    name = logic.html_escape(r["name"] or "—")
    id_text = (
        f'<a href="{logic.html_escape(user_card_start_url(bot_username, uid))}">{uid}</a>'
        if bot_username else f"<code>{uid}</code>"
    )
    return f"{index}. {id_text} · {uname} ({name})"


async def _show_users_list(context: ContextTypes.DEFAULT_TYPE, page: int, note: str = "") -> str:
    storage = context.bot_data["storage"]
    context.user_data["users_page"] = page
    total = storage.count()
    rows = storage.profiles_page(page * PAGE_SIZE, PAGE_SIZE)
    bot_username = context.bot.username
    lines = []
    if note:
        lines += [note, ""]
    lines += [
        "👤 <b>Пользователи</b>",
        "",
        "Пришлите Telegram ID (число) или @username участника, чтобы найти его "
        "(в том числе без анкеты) — или нажмите на ID в списке ниже.",
        "",
        f"📋 Известно системе (по анкетам): {total}",
    ]
    for i, r in enumerate(rows, start=page * PAGE_SIZE + 1):
        lines.append(_users_list_line(r, i, bot_username))
    if not rows and not total:
        lines.append("Пока никто не заполнил анкету.")
    await admin_ui.edit_screen(context, "\n".join(lines), _users_list_kb(page, total))
    return WAIT_LOOKUP


async def nav_users(update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await _show_users_list(context, 0)


async def usr_list_page(update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    page = int(update.callback_query.data.split(":", 1)[1])
    return await _show_users_list(context, page)


async def _resolve_user_id(context: ContextTypes.DEFAULT_TYPE, raw: str) -> int | None:
    raw = raw.strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    username = raw.lstrip("@").strip()
    if not username:
        return None
    storage = context.bot_data["storage"]
    for r in storage.search_profiles(username):
        if (r["username"] or "").lower() == username.lower():
            return r["user_id"]
    try:
        chat = await context.bot.get_chat(f"@{username}")
        return chat.id
    except Exception:  # noqa: BLE001
        return None


async def lookup_text(update, context: ContextTypes.DEFAULT_TYPE):
    raw = (update.message.text or "").strip()
    try:
        await update.message.delete()
    except Exception:  # noqa: BLE001
        pass
    user_id = await _resolve_user_id(context, raw)
    if user_id is None:
        page = context.user_data.get("users_page", 0)
        await _show_users_list(context, page, note=f"Не нашёл участника «{logic.html_escape(raw)}».")
        return WAIT_LOOKUP
    await _show_card(context, user_id)
    return BROWSE


# --- карточка участника ----------------------------------------------------

def _referral_lines(storage, user_id: int) -> list[str]:
    """Кто привёл этого юзера и кого привёл он сам — «в ответе за
    приглашённого»: видимость связи для админа, без автонаказаний."""
    lines = []
    referrer = storage.get_referrer_of(user_id)
    if referrer:
        lines.append(f"\n🔗 Приглашён(а) пользователем <code>{referrer['referrer_id']}</code>"
                      f" (слот {referrer['slot']})")
    invited = storage.list_invited_by(user_id)
    if invited:
        marks = []
        for r in invited:
            uid = r["invited_user_id"]
            mark = " ⛔" if storage.is_banned(uid) else ""
            marks.append(f"<code>{uid}</code>{mark}")
        banned_count = sum(1 for r in invited if storage.is_banned(r["invited_user_id"]))
        lines.append(
            f"\n👥 Сам(а) пригласил(а) {len(invited)} чел."
            + (f", из них забанено: {banned_count}" if banned_count else "")
            + f": {', '.join(marks)}"
        )
    return lines


def _card_text(storage, user_id: int, profile, member, banned: bool) -> str:
    lines = [f"👤 <b>Участник</b>\nTelegram: <code>{user_id}</code>"]
    if member is not None:
        uname = (
            f"@{logic.html_escape(member.user.username)}"
            if member.user.username else logic.html_escape(member.user.full_name)
        )
        lines.append(f"Имя: {uname}")
        lines.append(f"Статус в группе: {_STATUS_LABELS.get(member.status, str(member.status))}")
    else:
        lines.append("Статус в группе: неизвестен (не настроен COMMUNITY_CHAT_ID или не в группе)")
    if banned:
        lines.append("⛔ <b>ЗАБАНЕН администратором</b> — анкета не вернёт доступ автоматически")
    lines.extend(_referral_lines(storage, user_id))
    if profile:
        lines.append(
            f"\n📋 Анкета #{profile['id']}: {logic.html_escape(profile['vertical'])}/"
            f"{logic.html_escape(profile['grade'])}"
        )
    else:
        lines.append("\n📋 Анкеты нет")
    return "\n".join(lines)


def _card_kb(user_id: int, profile, member, banned: bool) -> InlineKeyboardMarkup:
    rows = []
    if profile:
        rows.append([InlineKeyboardButton("📋 Открыть анкету", callback_data=f"acms_pf_open:{profile['id']}")])
    is_admin_member = member is not None and member.status in (
        ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR,
    )
    is_restricted = banned or (member is not None and member.status in (
        ChatMemberStatus.RESTRICTED, ChatMemberStatus.BANNED,
    ))
    if not is_admin_member:
        if is_restricted:
            rows.append([InlineKeyboardButton(
                "🔓 Разбанить / снять мут", callback_data=f"acms_usr_unban:{user_id}",
            )])
        else:
            rows.append([
                InlineKeyboardButton(label, callback_data=f"acms_usr_mute:{user_id}:{i}")
                for i, (label, _delta) in enumerate(MUTE_OPTIONS)
            ])
            rows.append([InlineKeyboardButton(
                "⛔ Забанить (навсегда)", callback_data=f"acms_usr_ban_confirm:{user_id}",
            )])
    rows.append([InlineKeyboardButton("📩 Написать", url=f"tg://user?id={user_id}")])
    rows.append([InlineKeyboardButton("‹ Пользователи", callback_data="acms_users")])
    rows.append([InlineKeyboardButton("‹ Панель управления", callback_data="acms_home")])
    return InlineKeyboardMarkup(rows)


async def _member_for(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    settings = context.bot_data["settings"]
    if not settings.community_chat_id:
        return None
    try:
        return await context.bot.get_chat_member(settings.community_chat_id, user_id)
    except Exception:  # noqa: BLE001
        return None


async def _show_card(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    storage = context.bot_data["storage"]
    profile = storage.get_profile_by_telegram_id(user_id)
    member = await _member_for(context, user_id)
    banned = storage.is_banned(user_id)
    await admin_ui.edit_screen(
        context, _card_text(storage, user_id, profile, member, banned),
        _card_kb(user_id, profile, member, banned),
    )


async def send_card_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    """Открывает карточку участника НОВЫМ сообщением — вход извне обычной
    навигации /admin (форвард сообщения или deep-link `?start=u_<id>`).
    Предыдущий экран /admin (список и т.п.) при этом подчищается."""
    await admin_ui.delete_previous_screen(context)
    storage = context.bot_data["storage"]
    profile = storage.get_profile_by_telegram_id(user_id)
    member = await _member_for(context, user_id)
    banned = storage.is_banned(user_id)
    msg = await context.bot.send_message(
        chat_id, _card_text(storage, user_id, profile, member, banned),
        reply_markup=_card_kb(user_id, profile, member, banned), parse_mode=ParseMode.HTML,
    )
    await admin_ui.store_screen(context, msg)


async def usr_open(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = int(q.data.split(":", 1)[1])
    await _show_card(context, user_id)
    return BROWSE


async def usr_mute(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, uid_s, idx_s = q.data.split(":")
    user_id, idx = int(uid_s), int(idx_s)
    label, delta = MUTE_OPTIONS[idx]
    settings = context.bot_data["settings"]
    if not settings.community_chat_id:
        await q.answer("COMMUNITY_CHAT_ID не настроен в .env", show_alert=True)
        return BROWSE
    until = datetime.now(timezone.utc) + delta
    try:
        await context.bot.restrict_chat_member(
            settings.community_chat_id, user_id, permissions=_MUTED, until_date=until,
        )
    except Exception:  # noqa: BLE001
        await q.answer("Не удалось замутить — проверьте права бота", show_alert=True)
        return BROWSE
    context.bot_data["storage"].log_action(
        update.effective_user.id, "manual_mute", f"user_id={user_id} на {label}",
    )
    await q.answer(f"Мут на {label} выдан")
    await _show_card(context, user_id)
    return BROWSE


async def usr_ban_confirm(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = int(q.data.split(":", 1)[1])
    await admin_ui.edit_screen(
        context,
        f"Вы уверены, что хотите забанить участника <code>{user_id}</code>?\n\n"
        "Он не сможет писать в группе, пока не разбаните (это ограничение прав, "
        "не удаление из группы).",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, забанить", callback_data=f"acms_usr_ban:{user_id}")],
            [InlineKeyboardButton("‹ Отмена", callback_data=f"acms_usr_open:{user_id}")],
        ]),
    )
    return BROWSE


async def usr_ban(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = int(q.data.split(":", 1)[1])
    settings = context.bot_data["settings"]
    if not settings.community_chat_id:
        await q.answer("COMMUNITY_CHAT_ID не настроен в .env", show_alert=True)
        return BROWSE
    try:
        await context.bot.restrict_chat_member(settings.community_chat_id, user_id, permissions=_MUTED)
    except Exception:  # noqa: BLE001
        await q.answer("Не удалось забанить — проверьте права бота", show_alert=True)
        return BROWSE
    storage = context.bot_data["storage"]
    storage.ban_user(user_id)  # отдельно от group_mutes — анкета это не снимет
    storage.log_action(update.effective_user.id, "manual_ban", f"user_id={user_id}")
    referrer = storage.get_referrer_of(user_id)
    if referrer:
        referrer_id = referrer["referrer_id"]
        storage.log_action(
            update.effective_user.id, "referral_ban_flag",
            f"invited_user={user_id} referrer={referrer_id}",
        )
        await q.answer(
            f"Забанен. ⚠️ Его привёл пользователь {referrer_id} — проверьте его карточку "
            "(«Пользователи» → поиск по ID).",
            show_alert=True,
        )
    else:
        await q.answer("Забанен (ограничен навсегда)")
    await _show_card(context, user_id)
    return BROWSE


async def usr_unban(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = int(q.data.split(":", 1)[1])
    settings = context.bot_data["settings"]
    if not settings.community_chat_id:
        await q.answer("COMMUNITY_CHAT_ID не настроен в .env", show_alert=True)
        return BROWSE
    try:
        perms = await _chat_permissions(context, settings.community_chat_id)
        await context.bot.restrict_chat_member(settings.community_chat_id, user_id, permissions=perms)
    except Exception:  # noqa: BLE001
        await q.answer("Не удалось снять ограничения", show_alert=True)
        return BROWSE
    storage = context.bot_data["storage"]
    storage.unban_user(user_id)
    storage.log_action(update.effective_user.id, "manual_unban", f"user_id={user_id}")
    await q.answer("Разбанен / размучен")
    await _show_card(context, user_id)
    return BROWSE


# --- быстрый лукап: админ форвардит сообщение из группы -> карточка сразу ---

def _forwarded_sender_id(message) -> int | None:
    """id автора пересланного сообщения (для быстрого открытия карточки).

    Если у автора включена приватность форвардов (MessageOriginHiddenUser) —
    id недоступен, возвращаем None (как и для форварда из чата/канала)."""
    origin = getattr(message, "forward_origin", None)
    sender_user = getattr(origin, "sender_user", None)
    if sender_user and getattr(sender_user, "id", None):
        return int(sender_user.id)
    forward_from = getattr(message, "forward_from", None)  # legacy-поле старых версий Bot API
    if forward_from and getattr(forward_from, "id", None):
        return int(forward_from.id)
    return None


async def quick_lookup_forward(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ переслал в личку боту любое сообщение участника — сразу открываем
    его карточку, без захода в /admin (по образцу island_summary_bot)."""
    message = update.message
    user = update.effective_user
    settings = context.bot_data["settings"]
    if message is None or user is None or not settings.is_admin(user.id):
        return
    sender_id = _forwarded_sender_id(message)
    if sender_id is None:
        return
    await send_card_message(context, message.chat_id, sender_id)


def build_admin_users_handlers() -> list:
    """Хендлеры вне ConversationHandler-состояний (group=1 в bot.py) — работают
    независимо от того, есть ли у админа активная сессия /admin (см. докстринг
    модуля)."""
    return [
        MessageHandler(filters.ChatType.PRIVATE & filters.FORWARDED, quick_lookup_forward),
        CallbackQueryHandler(usr_open, pattern=r"^acms_usr_open:\d+$"),
        CallbackQueryHandler(usr_mute, pattern=r"^acms_usr_mute:\d+:\d+$"),
        CallbackQueryHandler(usr_ban_confirm, pattern=r"^acms_usr_ban_confirm:\d+$"),
        CallbackQueryHandler(usr_ban, pattern=r"^acms_usr_ban:\d+$"),
        CallbackQueryHandler(usr_unban, pattern=r"^acms_usr_unban:\d+$"),
    ]
