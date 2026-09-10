"""Оплата подписки GURO ID через Telegram Stars. Invoice-ссылку создаёт
guro_id_api.py (createInvoiceLink), но pre_checkout_query и successful_payment
прилетают только сюда (только bot.py поллит getUpdates)."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, PreCheckoutQueryHandler, filters

import community_access as CA
import guro_constants as GC
import guro_tags as GT

logger = logging.getLogger(__name__)

# product -> (payload-префикс, тарифная сетка). Кабинет рекрутера (Фаза 3,
# 12.08.2026) добавлен рядом с базовой подпиской — тот же payload-формат
# '<префикс>:<plan>:<user_id>', просто другой продукт/таблица активации.
# company_basic/company_pro (27.08.2026, ТЗ "Тарифы и лимиты") — два тира
# ОДНОГО кабинета "Компания", см. GC.COMPANY_TIER_*/_PRODUCT_COMPANY_TIER.
_PRODUCTS = {
    "guro_id": ("guro_id_subscription", GC.SUBSCRIPTION_PLANS),
    "recruiter": ("guro_id_recruiter_subscription", GC.RECRUITER_SUBSCRIPTION_PLANS),
    "company_basic": ("guro_id_company_basic_subscription", GC.COMPANY_BASIC_SUBSCRIPTION_PLANS),
    "company_pro": ("guro_id_company_pro_subscription", GC.COMPANY_PRO_SUBSCRIPTION_PLANS),
}
_PRODUCT_COMPANY_TIER = {"company_basic": GC.COMPANY_TIER_BASIC, "company_pro": GC.COMPANY_TIER_PRO}


def _match_payload(invoice_payload: str) -> tuple[str, dict] | None:
    """payload формата '<префикс>:<plan>:<user_id>'. Возвращает (product,
    plan_cfg) или None, если префикс не наш (чужой payload в проекте
    сейчас нет других invoice-флоу, но на всякий случай не отвечаем).
    Неизвестный/отсутствующий план -> тихо откатываемся на месячный (план
    валидируется ещё при создании инвойса в guro_id_api.py, это защита на
    случай рассинхрона версий фронта/бэкенда)."""
    for product, (prefix, plans) in _PRODUCTS.items():
        if invoice_payload.startswith(prefix + ":"):
            plan = invoice_payload[len(prefix) + 1:].split(":")[0]
            cfg = plans.get(plan)
            if cfg is None:
                logger.warning("guro_payments: неизвестный план '%s' для %s, откат на monthly", plan, product)
                cfg = plans["monthly"]
            return product, cfg
    return None


async def on_guro_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    if _match_payload(query.invoice_payload) is not None:
        await query.answer(ok=True)
    # чужой payload (в проекте сейчас нет других invoice-флоу) — намеренно не
    # отвечаем, чтобы не подтверждать чужой платёж по ошибке.


async def on_guro_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payment = update.message.successful_payment
    matched = _match_payload(payment.invoice_payload)
    if matched is None:
        return
    product, cfg = matched
    storage = context.bot_data["guro_storage"]

    if product == "recruiter":
        expires_at = storage.activate_recruiter_subscription(update.effective_user.id, cfg["duration_days"])
        await update.message.reply_text(
            f"✅ Кабинет рекрутера GURO ID активирован до {expires_at[:10]} — "
            "публикация вакансий и просмотр резюме открыты."
        )
        return

    if product in _PRODUCT_COMPANY_TIER:
        tier = _PRODUCT_COMPANY_TIER[product]
        expires_at = storage.activate_company_subscription(update.effective_user.id, cfg["duration_days"], tier=tier)
        await update.message.reply_text(
            f"✅ Кабинет компании GURO ID ({tier}) активирован до {expires_at[:10]} — "
            "бренд-страница работодателя открыта."
        )
        return

    expires_at = storage.activate_subscription(update.effective_user.id, cfg["duration_days"])
    await update.message.reply_text(
        f"✅ Подписка GURO ID активирована до {expires_at[:10]} — полный поиск и просмотр профилей открыты."
    )
    settings = context.bot_data["settings"]
    await _grant_community_if_paywalled(context, settings, update.effective_user.id)
    try:
        await GT.sync_member_tag(
            context.bot, settings.community_chat_id, storage, update.effective_user.id,
            reason="subscription_activated",
        )
    except Exception:  # noqa: BLE001
        logger.exception("guro_payments: tag sync failed for user %s", update.effective_user.id)


async def _grant_community_if_paywalled(context, settings, user_id: int) -> None:
    """Оплата открывает ещё и вход в сообщество (09.09.2026).

    Только тем, кто пришёл через платный вход. У старых участников стоит
    признак «доступ без оплаты», они уже в группе, и одноразовая ссылка
    после продления подписки звала бы внутрь того, кто внутри давно.
    """
    main_storage = context.bot_data["storage"]
    if main_storage.has_community_access(user_id):
        return
    content = context.bot_data["content"]
    await CA.grant_access(
        context.bot, settings, user_id,
        content.txt("paywall_granted"),
        content.btn("join"), content.btn("guro_id"),
    )


def build_guro_payments_handlers() -> list:
    return [
        PreCheckoutQueryHandler(on_guro_pre_checkout),
        MessageHandler(filters.SUCCESSFUL_PAYMENT, on_guro_successful_payment),
    ]
