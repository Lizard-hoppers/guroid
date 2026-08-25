"""Обработка кнопок Подтвердить/Отклонить под уведомлением о партнёрстве GURO
ID. Уведомление шлёт guro_id_api.py (одноразовый Bot(token=...)), но ответ на
inline-кнопку обязан обработать ЭТОТ процесс — только bot.py поллит
getUpdates, второй поллинг на тот же токен получил бы 409 Conflict."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

logger = logging.getLogger(__name__)

_ERROR_ALERTS = {
    "NOT_FOUND": "Партнёрство не найдено.",
    "NOT_YOUR_REQUEST": "Это приглашение адресовано не вам.",
    "ALREADY_RESOLVED": "Уже обработано.",
}


async def cb_guro_partnership_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    action, partnership_id = q.data.split(":")[1:]
    accept = action == "confirm"
    storage = context.bot_data["guro_storage"]

    try:
        row = storage.respond_partnership(int(partnership_id), responder_id=q.from_user.id, accept=accept)
    except ValueError as e:
        await q.answer(_ERROR_ALERTS.get(str(e), "Не получилось обработать."), show_alert=True)
        return

    await q.answer()
    if accept:
        await q.edit_message_text(
            "✅ Партнёрство подтверждено. Запись появится в профилях обоих в GURO ID. "
            "Не забудьте оценить сотрудничество в приложении (раздел «Мой рейтинг»)."
        )
    else:
        await q.edit_message_text("❌ Партнёрство отклонено.")

    confirmer_mention = f"@{q.from_user.username}" if q.from_user.username else q.from_user.full_name
    text = (
        f"✅ {confirmer_mention} подтвердил(а) партнёрство с вами в GURO ID."
        if accept else
        f"❌ {confirmer_mention} отклонил(а) заявку на партнёрство в GURO ID."
    )
    try:
        await context.bot.send_message(row["initiator_id"], text)
    except Exception:  # noqa: BLE001
        logger.debug("guro_partnerships: не удалось уведомить инициатора %s", row["initiator_id"], exc_info=True)


def build_guro_partnerships_handlers() -> list:
    return [CallbackQueryHandler(cb_guro_partnership_response, pattern=r"^guro:(confirm|decline):\d+$")]
