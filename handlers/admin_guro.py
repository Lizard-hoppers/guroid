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


def _dashboard_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚩 Подозрительная активность", callback_data="acms_guro_flagged")],
        [InlineKeyboardButton("🏢 Адреса компаний на проверку", callback_data="acms_guro_addr")],
        [InlineKeyboardButton("‹ Панель управления", callback_data="acms_home")],
    ])


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
    await admin_ui.edit_screen(context, text, _dashboard_kb())
    return admin_ui.BROWSE


# --- антифрод поиска (ТЗ 7.3, 25.08.2026) — подозрительная активность -----

def _flagged_row_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❄️ Заморозить на 24ч", callback_data=f"guro_freeze:{user_id}"),
        InlineKeyboardButton("✅ Снять флаг", callback_data=f"guro_unflag:{user_id}"),
    ]])


async def nav_guro_flagged(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    guro = context.bot_data["guro_storage"]
    rows = guro.list_flagged_accounts()
    if not rows:
        await admin_ui.edit_screen(context, "🚩 Подозрительной активности не найдено.", _back_kb())
        return admin_ui.BROWSE

    lines = ["🚩 <b>Подозрительная активность (скрапинг поиска)</b>\n"]
    kb_rows = []
    for row in rows[:15]:
        frozen = " · ❄️ заморожен" if guro.is_frozen(row["user_id"]) else ""
        lines.append(f"• <code>{row['user_id']}</code> — флаг {row['scraping_flagged_at']}{frozen}")
        kb_rows.append([
            InlineKeyboardButton(f"❄️ {row['user_id']}", callback_data=f"guro_freeze:{row['user_id']}"),
            InlineKeyboardButton(f"✅ {row['user_id']}", callback_data=f"guro_unflag:{row['user_id']}"),
        ])
    kb_rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_guro")])
    await admin_ui.edit_screen(context, "\n".join(lines), InlineKeyboardMarkup(kb_rows))
    return admin_ui.BROWSE


async def guro_freeze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer("Заморожено на 24ч")
    guro = context.bot_data["guro_storage"]
    user_id = int(q.data.split(":")[1])
    guro.freeze_account(user_id)
    return await nav_guro_flagged(update, context)


async def guro_unflag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer("Флаг снят")
    guro = context.bot_data["guro_storage"]
    user_id = int(q.data.split(":")[1])
    guro.unfreeze_account(user_id)
    return await nav_guro_flagged(update, context)


# --- верификация адреса компании (ТЗ 5.5, 25.08.2026) ----------------------

def _addr_row_kb(address_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Одобрить", callback_data=f"guro_addr_ok:{address_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"guro_addr_no:{address_id}"),
    ]])


async def nav_guro_addresses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    guro = context.bot_data["guro_storage"]
    rows = guro.list_pending_company_addresses()
    if not rows:
        await admin_ui.edit_screen(context, "🏢 Адресов на проверку нет.", _back_kb())
        return admin_ui.BROWSE

    lines = ["🏢 <b>Адреса компаний на проверку</b>\n"]
    kb_rows = []
    for row in rows[:15]:
        lines.append(f"• #{row['id']} компания <code>{row['company_user_id']}</code> — {row['network']}: <code>{row['address']}</code>")
        kb_rows.append([
            InlineKeyboardButton(f"✅ #{row['id']}", callback_data=f"guro_addr_ok:{row['id']}"),
            InlineKeyboardButton(f"❌ #{row['id']}", callback_data=f"guro_addr_no:{row['id']}"),
        ])
    kb_rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_guro")])
    await admin_ui.edit_screen(context, "\n".join(lines), InlineKeyboardMarkup(kb_rows))
    return admin_ui.BROWSE


async def guro_addr_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    approve = q.data.startswith("guro_addr_ok:")
    address_id = int(q.data.split(":")[1])
    guro = context.bot_data["guro_storage"]
    ok = guro.review_company_address(address_id, update.effective_user.id, approve)
    await q.answer("Одобрено" if approve and ok else ("Отклонено" if ok else "Уже обработано"))
    return await nav_guro_addresses(update, context)
