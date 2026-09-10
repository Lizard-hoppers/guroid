"""Раздел /admin «Анкеты»: постраничный список (компактный, кликабельный
Telegram ID — по образцу island_summary_bot) + поиск + карточка анкеты с
действиями (замена голому /export для повседневной работы с заявками).

WAIT_SEARCH — собственная строковая константа состояния ConversationHandler
(не пересекается с int-состояниями admin_cms.py; PTB допускает произвольные
hashable-ключи состояний).

Карточка анкеты открывается либо кликом по ID в списке (deep-link
`?start=p_<id>`, см. flow.start), либо кнопкой из результатов поиска. Кнопки
самой карточки (contact/unmute) — ВНЕ ConversationHandler-состояний
(build_admin_profiles_handlers, group=1 в bot.py), т.к. карточка может быть
первым сообщением для админа без активной сессии /admin (тот же приём, что и
в admin_users.py — см. докстринг там)."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, ContextTypes

import community_access as CA
import logic
from handlers import admin_ui
from handlers import group_captcha as gate
from handlers.admin_ui import BROWSE

PAGE_SIZE = 20
WAIT_SEARCH = "pf:search"


class _MinimalUser:
    """Достаточно полей для _mention()/_send_greeting() в group_captcha.py."""

    def __init__(self, user_id: int, username: str):
        self.id = user_id
        self.username = username
        self.full_name = username or str(user_id)


def profile_card_start_url(bot_username: str, profile_id: int) -> str:
    """Deep-link, по клику на который бот сразу открывает карточку анкеты."""
    return f"https://t.me/{bot_username}?start=p_{profile_id}"


def _list_line(r, index: int, bot_username: str | None) -> str:
    mark = "✅" if r["contacted"] else ""
    name = logic.html_escape(r["name"] or "—")
    uid = r["user_id"]
    id_text = (
        f'<a href="{logic.html_escape(profile_card_start_url(bot_username, r["id"]))}">{uid}</a>'
        if bot_username else f"<code>{uid}</code>"
    )
    return (
        f"{index}. {mark}#{r['id']} · {id_text} · {name} · "
        f"{logic.html_escape(r['vertical'])}/{logic.html_escape(r['grade'])}"
    )


def _list_kb(page: int, total: int, query: str | None) -> InlineKeyboardMarkup:
    kb_rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("← Назад", callback_data=f"acms_pf_list:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("Вперёд →", callback_data=f"acms_pf_list:{page + 1}"))
    if nav:
        kb_rows.append(nav)
    if not query:
        kb_rows.append([InlineKeyboardButton("🔍 Поиск", callback_data="acms_pf_search")])
    else:
        kb_rows.append([InlineKeyboardButton("✖ Сбросить поиск", callback_data="acms_pf")])
    kb_rows.append([InlineKeyboardButton("‹ Панель управления", callback_data="acms_home")])
    return InlineKeyboardMarkup(kb_rows)


async def _show_list(context: ContextTypes.DEFAULT_TYPE, page: int,
                      query: str | None = None) -> None:
    storage = context.bot_data["storage"]
    context.user_data["pf_page"] = page
    context.user_data["pf_query"] = query
    bot_username = context.bot.username
    if query:
        rows = storage.search_profiles(query)
        total = len(rows)
        rows = rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
        header = f"📋 <b>Анкеты</b> — поиск «{logic.html_escape(query)}» ({total}):"
        if not rows:
            header = f"📋 По запросу «{logic.html_escape(query)}» ничего не найдено."
    else:
        total = storage.count()
        rows = storage.profiles_page(page * PAGE_SIZE, PAGE_SIZE)
        header = f"📋 <b>Анкеты</b> (всего {total}):"
    lines = [header, ""]
    for i, r in enumerate(rows, start=page * PAGE_SIZE + 1):
        lines.append(_list_line(r, i, bot_username))
    await admin_ui.edit_screen(context, "\n".join(lines), _list_kb(page, total, query))


async def nav_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await _show_list(context, 0, None)
    return BROWSE


async def pf_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    page = int(update.callback_query.data.split(":", 1)[1])
    await _show_list(context, page, context.user_data.get("pf_query"))
    return BROWSE


async def pf_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await admin_ui.edit_screen(
        context,
        "🔍 Пришлите ID анкеты, Telegram ID, @username, имя, вертикаль или "
        "компанию для поиска.",
        InlineKeyboardMarkup([[InlineKeyboardButton("‹ Назад", callback_data="acms_pf")]]),
    )
    return WAIT_SEARCH


async def pf_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    try:
        await update.message.delete()
    except Exception:  # noqa: BLE001
        pass
    if not query:
        return BROWSE
    await _show_list(context, 0, query)
    return BROWSE


def _access_line(context, user_id: int) -> str:
    """Строка «Вход в сообщество» (09.09.2026, платный вход). Три состояния:
    освобождён (старые участники и ручные выдачи), по подписке, не оплачен."""
    if context.bot_data["storage"].has_community_access(user_id):
        return "Вход в сообщество: 🎟 без оплаты"
    guro = context.bot_data.get("guro_storage")
    if guro is not None and guro.is_subscribed(user_id):
        return "Вход в сообщество: 💳 по подписке (активна)"
    return "Вход в сообщество: ⛔ не оплачен"


def _card_text(r, mute_chats: list[int], access_line: str = "") -> str:
    lines = [
        f"📋 <b>Анкета #{r['id']}</b>\n",
        f"Дата: {r['created_at']}",
        f"Telegram: <code>{r['user_id']}</code>"
        + (f" (@{logic.html_escape(r['username'])})" if r["username"] else ""),
        f"Вертикаль/грейд: {logic.html_escape(r['vertical'])} / {logic.html_escape(r['grade'])}",
        f"Профессия: {logic.html_escape(r['profession'] or '—')}",
    ]
    if r["investor_type"]:
        lines.append(f"Инвестор: {logic.html_escape(r['investor_type'])}")
        lines.append(f"Сумма: {logic.html_escape(r['investor_amount'] or '—')}")
        lines.append(f"Интересы: {logic.html_escape(r['investor_needs'] or '—')}")
    lines += [
        f"Запрос: {logic.html_escape(r['request'] or '—')}",
        f"Имя: {logic.html_escape(r['name'] or '—')}",
        f"Компания: {logic.html_escape(r['company'] or '—')}",
        f"LinkedIn: {logic.html_escape(r['linkedin'] or '—')}",
        "",
        f"Связались: {'✅ да' if r['contacted'] else '⬜ нет'}",
    ]
    if access_line:
        lines.append(access_line)
    if mute_chats:
        lines.append(f"🔒 Замучен гейтом в {len(mute_chats)} чате(ах)")
    if r["blocked"]:
        lines.append("🚫 Заблокировал бота (рассылки пропускают)")
    return "\n".join(lines)


def _card_kb(r, mute_chats: list[int], sheets_url: str | None, back_page: int,
             access_granted: bool = False) -> InlineKeyboardMarkup:
    rows = []
    contact_label = "⬜ Пометить: связались" if not r["contacted"] else "✅ Связались (убрать отметку)"
    rows.append([InlineKeyboardButton(contact_label, callback_data=f"acms_pf_contact:{r['id']}")])
    # Платный вход (09.09.2026): «для своих этот шаг оплаты не проходить».
    access_label = "✖ Снять доступ без оплаты" if access_granted else "🎟 Пустить без оплаты"
    rows.append([InlineKeyboardButton(access_label, callback_data=f"acms_pf_access:{r['id']}")])
    if mute_chats:
        rows.append([InlineKeyboardButton("🔓 Размутить в группе", callback_data=f"acms_pf_unmute:{r['id']}")])
    action_row = [InlineKeyboardButton("📩 Написать", url=f"tg://user?id={r['user_id']}")]
    if sheets_url:
        action_row.append(InlineKeyboardButton("📊 Sheets", url=sheets_url))
    rows.append(action_row)
    rows.append([InlineKeyboardButton("‹ К списку", callback_data=f"acms_pf_list:{back_page}")])
    return InlineKeyboardMarkup(rows)


def _sheets_url(context) -> str | None:
    settings = context.bot_data["settings"]
    if settings.google_sheets_enabled and settings.google_sheets_spreadsheet_id:
        return f"https://docs.google.com/spreadsheets/d/{settings.google_sheets_spreadsheet_id}"
    return None


async def _show_card(context, profile_id: int):
    storage = context.bot_data["storage"]
    r = storage.get_profile(profile_id)
    if r is None:
        await admin_ui.edit_screen(
            context, "Анкета не найдена (возможно, удалена).",
            InlineKeyboardMarkup([[InlineKeyboardButton("‹ К списку", callback_data="acms_pf")]]),
        )
        return
    mute_chats = storage.user_mute_chats(r["user_id"])
    back_page = context.user_data.get("pf_page", 0)
    await admin_ui.edit_screen(
        context, _card_text(r, mute_chats, _access_line(context, r["user_id"])),
        _card_kb(r, mute_chats, _sheets_url(context), back_page,
                 storage.has_community_access(r["user_id"])),
    )


async def send_card_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, profile_id: int) -> None:
    """Открывает карточку анкеты НОВЫМ сообщением — вход по deep-link
    `?start=p_<id>` (клик по ID в списке), без активной сессии /admin.
    Предыдущий экран /admin (список и т.п.) при этом подчищается."""
    await admin_ui.delete_previous_screen(context)
    storage = context.bot_data["storage"]
    r = storage.get_profile(profile_id)
    if r is None:
        await context.bot.send_message(chat_id, "Анкета не найдена (возможно, удалена).")
        return
    mute_chats = storage.user_mute_chats(r["user_id"])
    msg = await context.bot.send_message(
        chat_id, _card_text(r, mute_chats, _access_line(context, r["user_id"])),
        reply_markup=_card_kb(r, mute_chats, _sheets_url(context), 0,
                              storage.has_community_access(r["user_id"])),
        parse_mode=ParseMode.HTML,
    )
    await admin_ui.store_screen(context, msg)


async def pf_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    pid = int(update.callback_query.data.split(":", 1)[1])
    await _show_card(context, pid)
    return BROWSE


async def pf_toggle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    pid = int(q.data.split(":", 1)[1])
    storage = context.bot_data["storage"]
    r = storage.get_profile(pid)
    if r is None:
        await q.answer("Анкета не найдена", show_alert=True)
        return BROWSE
    new_val = not bool(r["contacted"])
    storage.set_contacted(pid, new_val)
    storage.log_action(
        update.effective_user.id, "contacted",
        f"анкета #{pid}: {'отмечена как связались' if new_val else 'снята отметка'}",
    )
    await q.answer("Отмечено" if new_val else "Отметка снята")
    await _show_card(context, pid)
    return BROWSE


async def pf_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    pid = int(q.data.split(":", 1)[1])
    storage = context.bot_data["storage"]
    r = storage.get_profile(pid)
    if r is None:
        await q.answer("Анкета не найдена", show_alert=True)
        return BROWSE
    user = _MinimalUser(r["user_id"], r["username"] or "")
    await gate.unmute_after_profile(context, user)
    storage.log_action(update.effective_user.id, "force_unmute", f"анкета #{pid}, user_id={r['user_id']}")
    await q.answer("Размучен ✅")
    await _show_card(context, pid)
    return BROWSE


async def grant_access_by_admin(context, admin_id: int, user_id: int) -> str:
    """Общая часть кнопки карточки и /guro_access: ставит признак, пишет в
    журнал действий и сразу отправляет человеку ссылку в группу. Возвращает
    короткий итог для ответа админу."""
    storage = context.bot_data["storage"]
    if not storage.grant_community_access(user_id):
        return "Анкеты нет — доступ выдавать нечему"
    storage.log_action(admin_id, "community_access_grant", f"user_id={user_id}: пущен без оплаты")
    content = context.bot_data["content"]
    delivered = await CA.grant_access(
        context.bot, context.bot_data["settings"], user_id,
        content.txt("paywall_admin_granted"), content.btn("join"), content.btn("guro_id"),
    )
    return "Доступ выдан, ссылка отправлена ✅" if delivered else "Доступ выдан, но ссылку доставить не удалось (бот заблокирован?)"


async def pf_toggle_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    pid = int(q.data.split(":", 1)[1])
    storage = context.bot_data["storage"]
    r = storage.get_profile(pid)
    if r is None:
        await q.answer("Анкета не найдена", show_alert=True)
        return BROWSE
    if storage.has_community_access(r["user_id"]):
        storage.revoke_community_access(r["user_id"])
        storage.log_action(update.effective_user.id, "community_access_revoke",
                           f"анкета #{pid}, user_id={r['user_id']}: освобождение снято")
        await q.answer("Освобождение снято — теперь по общему правилу")
    else:
        await q.answer(await grant_access_by_admin(context, update.effective_user.id, r["user_id"]))
    await _show_card(context, pid)
    return BROWSE


def build_admin_profiles_handlers() -> list:
    """Кнопки карточки анкеты вне ConversationHandler-состояний (group=1 в
    bot.py) — работают и без активной сессии /admin (см. докстринг модуля)."""
    return [
        CallbackQueryHandler(pf_open, pattern=r"^acms_pf_open:\d+$"),
        CallbackQueryHandler(pf_toggle_contact, pattern=r"^acms_pf_contact:\d+$"),
        CallbackQueryHandler(pf_unmute, pattern=r"^acms_pf_unmute:\d+$"),
        CallbackQueryHandler(pf_toggle_access, pattern=r"^acms_pf_access:\d+$"),
    ]
