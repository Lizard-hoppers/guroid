"""Раздел «🪪 GURO ID» дашборда /admin — статистика по партнёрствам/репутации/
подписке. Только чтение (сам GURO ID живёт в отдельном сервисе guro_id_api.py
и в handlers/guro_partnerships.py, guro_payments.py) — здесь просто витрина
цифр поверх той же БД, без дублирования модуля (Clean & Live Manifest)."""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from handlers import admin_ui

logger = logging.getLogger(__name__)


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("‹ Панель управления", callback_data="acms_home")]])


async def _stars_line(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Заработано звёзд — через нативный реестр Telegram Stars (у бота нет
    своей таблицы платежей, см. аналогичное решение в Taki Vmeste). Отдаёт
    последние до 100 операций — на старте продукта этого достаточно."""
    try:
        tx = await context.bot.get_star_transactions(limit=100)
        earned = sum(t.amount for t in tx.transactions if t.amount > 0)
        return f"\n⭐ Звёзд получено (последние операции): {earned}"
    except Exception:  # noqa: BLE001
        logger.debug("admin_guro: get_star_transactions failed", exc_info=True)
        return ""


async def nav_guro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    guro = context.bot_data["guro_storage"]
    s = guro.dashboard_stats()

    text = (
        "🪪 <b>GURO ID — статистика</b>\n\n"
        f"Партнёрств всего: <b>{s['total']}</b>\n"
        f"  ├ подтверждено: {s['confirmed']}\n"
        f"  ├ в ожидании: {s['pending']}\n"
        f"  └ отклонено: {s['declined']}\n"
        f"Новых заявок сегодня: {s['created_today']}\n\n"
        f"Отслеживается пользователей: {s['tracked_users']}\n"
        f"Средняя репутация: {s['avg_reputation']:.1f}\n"
        f"Активных подписок: {s['active_subscriptions']}"
        f"{await _stars_line(context)}"
    )
    await admin_ui.edit_screen(context, text, _back_kb())
    return admin_ui.BROWSE
