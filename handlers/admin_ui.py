"""Общий хелпер экранов /admin: единая панель (Clean Chat), редактируемая на
месте — используется admin_cms.py и разделами Анкеты/Рассылка/Журнал.
"""
from __future__ import annotations

import logging

from telegram.constants import ParseMode
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

# Общее состояние ConversationHandler «просто листаем экраны без ожидания
# ввода» — используется во всех разделах /admin, вынесено сюда, чтобы
# submodule'и (admin_profiles.py и др.) не импортировали admin_cms.py напрямую.
BROWSE = 0


async def store_screen(context, msg) -> None:
    context.user_data["adm_chat"] = msg.chat_id
    context.user_data["adm_mid"] = msg.message_id


async def delete_previous_screen(context) -> None:
    """Чистит предыдущий экран /admin перед отправкой НОВЫМ сообщением (не
    edit) — карточка по клику на ID в списке/форварду иначе оставляет старое
    меню висеть в чате рядом с новым."""
    chat = context.user_data.get("adm_chat")
    mid = context.user_data.get("adm_mid")
    if chat is None or mid is None:
        return
    try:
        await context.bot.delete_message(chat_id=chat, message_id=mid)
    except Exception:  # noqa: BLE001
        logger.debug("admin: не удалось удалить предыдущий экран", exc_info=True)


async def edit_screen(context, text: str, kb=None) -> bool:
    try:
        await context.bot.edit_message_text(
            text,
            chat_id=context.user_data["adm_chat"],
            message_id=context.user_data["adm_mid"],
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return True
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return True
        logger.debug("admin edit failed", exc_info=True)
        return False
