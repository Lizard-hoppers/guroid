"""Раздел /admin «Журнал» — постраничный просмотр admin_audit_log.

Действия пишут storage.log_action(...) сами разделы (Анкеты, Рассылка,
Режимы, Сплетни, Новости) — этот модуль только читает и рендерит.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import logic
from handlers import admin_ui
from handlers.admin_ui import BROWSE

PAGE_SIZE = 10

_ACTION_LABELS = {
    "broadcast": "📢 рассылка",
    "contacted": "📋 отметка «связались»",
    "force_unmute": "🔓 принудительный размут",
    "gate_toggle": "🔒 гейт",
    "greeting_toggle": "👋 приветствие",
    "gossip_toggle": "🗣 сплетни (тумблер)",
    "gossip_publish": "🗣 сплетня опубликована",
    "gossip_reject": "🗣 сплетня отклонена",
    "news_publish": "📰 новость опубликована",
    "news_reject": "📰 новость отклонена",
}


def _line(r) -> str:
    label = _ACTION_LABELS.get(r["action"], r["action"])
    detail = logic.html_escape(r["detail"] or "")
    return f"<b>{r['created_at']}</b> · admin {r['admin_id']} · {label}\n{detail}"


def _list_kb(page: int, total: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("← Назад", callback_data=f"acms_log_p:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("Вперёд →", callback_data=f"acms_log_p:{page + 1}"))
    rows = [nav] if nav else []
    rows.append([InlineKeyboardButton("‹ Панель управления", callback_data="acms_home")])
    return InlineKeyboardMarkup(rows)


async def _show_log(context, page: int) -> None:
    storage = context.bot_data["storage"]
    total = storage.audit_log_count()
    rows = storage.audit_log_page(page * PAGE_SIZE, PAGE_SIZE)
    if rows:
        body = "\n\n".join(_line(r) for r in rows)
    else:
        body = "Пока пусто — здесь будут появляться действия админов."
    text = f"📝 <b>Журнал действий</b> (всего {total})\n\n{body}"
    await admin_ui.edit_screen(context, text, _list_kb(page, total))


async def nav_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await _show_log(context, 0)
    return BROWSE


async def log_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    page = int(update.callback_query.data.split(":", 1)[1])
    await _show_log(context, page)
    return BROWSE
