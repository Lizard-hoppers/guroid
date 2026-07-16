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
