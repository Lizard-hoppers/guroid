"""Оплата подписки GURO ID через Telegram Stars. Invoice-ссылку создаёт
guro_id_api.py (createInvoiceLink), но pre_checkout_query и successful_payment
прилетают только сюда (только bot.py поллит getUpdates)."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, PreCheckoutQueryHandler, filters

import guro_tags as GT

logger = logging.getLogger(__name__)

_PAYLOAD_PREFIX = "guro_id_subscription:"


async def on_guro_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    if query.invoice_payload.startswith(_PAYLOAD_PREFIX):
        await query.answer(ok=True)
    # чужой payload (в проекте сейчас нет других invoice-флоу) — намеренно не
    # отвечаем, чтобы не подтверждать чужой платёж по ошибке.


async def on_guro_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payment = update.message.successful_payment
    if not payment.invoice_payload.startswith(_PAYLOAD_PREFIX):
        return
    storage = context.bot_data["guro_storage"]
    expires_at = storage.activate_subscription(update.effective_user.id)
    await update.message.reply_text(
        f"✅ Подписка GURO ID активирована до {expires_at[:10]} — полный поиск и просмотр профилей открыты."
    )
    settings = context.bot_data["settings"]
    try:
        await GT.sync_member_tag(
            context.bot, settings.community_chat_id, storage, update.effective_user.id,
            reason="subscription_activated",
        )
    except Exception:  # noqa: BLE001
        logger.exception("guro_payments: tag sync failed for user %s", update.effective_user.id)


def build_guro_payments_handlers() -> list:
    return [
        PreCheckoutQueryHandler(on_guro_pre_checkout),
        MessageHandler(filters.SUCCESSFUL_PAYMENT, on_guro_successful_payment),
    ]
