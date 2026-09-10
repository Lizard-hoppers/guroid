"""Экран оплаты входа в сообщество — кнопки под ним (09.09.2026).

Владелец: «подписку гуро айди дублируем в бот, и пока они не оплатят
подписку, в группу комьюнити не попадут; приоритет на криптооплату».

ЭТО ТА ЖЕ САМАЯ ПОДПИСКА GURO ID, а не отдельный продукт. Отсюда и
payload инвойса берётся тот же (guro_id_subscription:<план>:<id>), и
подтверждение обрабатывают уже существующие места: звёзды — handlers/
guro_payments.py, крипта — вебхук в guro_id_api.py. Заводить второй
продукт значило бы завести вторую цену, второй срок и второй список мест,
где подписку надо активировать, ради одной и той же покупки.

СОСТОЯНИЯ НЕТ НАМЕРЕННО. Кнопки несут всё нужное прямо в callback_data
(`paywall:<способ>:<план>`), поэтому сообщение с ними работает и через
неделю, и после перезапуска бота, и после того как анкета давно закрыта
(flow.py чистит user_data сразу после показа экрана). Человек, нажавший
«Оплачу позже», возвращается к оплате той же кнопкой, ничего не заполняя
заново.
"""
from __future__ import annotations

import logging

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice,
                      Update)
from telegram.ext import CallbackQueryHandler, ContextTypes

import guro_constants as GC
import guro_crypto as GCR
import ui

logger = logging.getLogger(__name__)

# Тот же payload, что и у оплаты из мини-приложения, — подтверждение
# обрабатывают уже существующие обработчики, см. шапку модуля.
_PAYLOAD_PREFIX = "guro_id_subscription"


def _plan(plan_key: str) -> dict | None:
    return GC.SUBSCRIPTION_PLANS.get(plan_key)


async def _send_stars_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE,
                              plan_key: str, cfg: dict) -> None:
    """Нативный инвойс Telegram Stars отдельным сообщением.

    Именно отдельным, а не правкой экрана оплаты: инвойс — особый тип
    сообщения, из обычного текста он не редактируется. Заодно экран с
    кнопками остаётся на месте, и передумавший может выбрать другой способ.
    """
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=f"GURO ID ({cfg['label'].lower()})",
        description="Доступ в сообщество GURO и приложение GURO ID.",
        payload=f"{_PAYLOAD_PREFIX}:{plan_key}:{update.effective_user.id}",
        provider_token=None,  # для Stars не нужен (Bot API 7.4+)
        currency="XTR",
        prices=[LabeledPrice(f"GURO ID — {cfg['label']}", cfg["stars_price"])],
    )


async def _send_crypto_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE,
                               plan_key: str, cfg: dict) -> None:
    """Счёт в USDT через CryptoBot — ссылкой на оплату.

    Кольцо распределения между двумя приложениями CryptoBot общее с мини-
    приложением (позиция лежит в БД), поэтому счёт из бота и счёт из
    приложения идут в одну очередь, а не сбивают пропорцию 5:1.
    """
    settings, storage = context.bot_data["settings"], context.bot_data["guro_storage"]
    picked = GCR.pick_token(settings, storage)
    if picked is None:
        await context.bot.send_message(
            update.effective_chat.id,
            "Оплата в крипте сейчас недоступна — выберите оплату звёздами.",
        )
        return
    token, token_label = picked
    amount = round(cfg["stars_price"] * GC.STARS_TO_USD_RATE, 2)
    try:
        invoice = await GCR.create_invoice(
            token,
            asset=GC.CRYPTO_ASSET,
            amount=amount,
            description=f"GURO ID ({cfg['label'].lower()})",
            payload=f"{_PAYLOAD_PREFIX}:{plan_key}:{update.effective_user.id}",
        )
    except GCR.CryptoBotError:
        logger.exception("paywall: не удалось создать crypto-инвойс (token=%s) для %s план=%s",
                         token_label, update.effective_user.id, plan_key)
        await context.bot.send_message(
            update.effective_chat.id,
            "Не получилось создать счёт — попробуйте ещё раз или оплатите звёздами.",
        )
        return

    pay_url = (invoice.get("pay_url") or invoice.get("bot_invoice_url")
               or invoice.get("mini_app_invoice_url"))
    await context.bot.send_message(
        update.effective_chat.id,
        f"Счёт на {amount} {GC.CRYPTO_ASSET} — {cfg['label'].lower()}.\n\n"
        "Оплатите по кнопке ниже. Доступ придёт сюда же сразу после оплаты.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Оплатить в крипте", url=pay_url)]]
        ) if pay_url else None,
    )


async def on_paywall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")  # paywall:<способ>:<план> | paywall:later
    action = parts[1] if len(parts) > 1 else ""
    content = context.bot_data["content"]

    if action == "later":
        # Кнопки оплаты дублируем в ответ: экран анкеты давно закрыт, и это
        # сообщение становится для человека постоянной точкой возврата.
        await context.bot.send_message(
            update.effective_chat.id, content.txt("paywall_later"),
            reply_markup=ui.paywall_kb(content),
        )
        return

    plan_key = parts[2] if len(parts) > 2 else ""
    cfg = _plan(plan_key)
    if cfg is None:
        logger.warning("paywall: неизвестный план '%s' от user_id=%s", plan_key,
                       update.effective_user.id)
        return

    if action == "crypto":
        await _send_crypto_invoice(update, context, plan_key, cfg)
    elif action == "stars":
        await _send_stars_invoice(update, context, plan_key, cfg)


def build_paywall_handlers() -> list:
    return [CallbackQueryHandler(on_paywall, pattern=r"^paywall:")]
