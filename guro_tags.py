"""GURO ID — статус-тег участника в чате (Bot API 22.7+, setChatMemberTag).
Показывает АКТИВНУЮ ПОДПИСКУ GURO ID прямо у имени в сообщениях в группе —
доступно ЛЮБОМУ обычному участнику (не только админам, в отличие от custom
title), поэтому не упирается в лимит ~50 админов на группу (см. project
memory / rating.py у Island Summary Bot — тот же паттерн, там тегом
показывается репутация, здесь — статус подписки). Сам факт наличия анкеты/
захода в Mini App тега НЕ даёт — это дефолтное условие для всех в
сообществе, тег обозначает именно платящего подписчика.

Три точки вызова:
- guro_id_api.py (handle_me) — освежает тег при каждом открытии профиля
  в Mini App (в т.ч. сразу проявляет его, если подписка только что куплена);
- handlers/guro_payments.py (on_guro_successful_payment) — сразу ставит тег
  после оплаты подписки, не дожидаясь следующего открытия Mini App;
- guro_tags_sync.py (systemd timer) — периодически снимает тег при истечении
  подписки (единственное событие без триггера в реальном времени) и
  подчищает то, что не долетело сразу (сеть/лимиты)."""
from __future__ import annotations

import asyncio
import logging

from telegram import Bot
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError

import guro_constants as GC
from guro_storage import GuroStorage

logger = logging.getLogger(__name__)

_SKIP_STATUSES = {
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.OWNER,
    ChatMemberStatus.LEFT,
    ChatMemberStatus.BANNED,
}


def target_tag(storage: GuroStorage, user_id: int) -> str:
    """Пустая строка = тега быть не должно (нет активной подписки)."""
    return GC.GURO_TAG if storage.is_subscribed(user_id) else ""


async def sync_member_tag(
    bot: Bot, chat_id: int, storage: GuroStorage, user_id: int, *, reason: str = ""
) -> None:
    if not chat_id:
        return
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramError:
        logger.info(
            "guro_tags: не удалось получить участника chat_id=%s user_id=%s reason=%s",
            chat_id, user_id, reason, exc_info=True,
        )
        return

    if member.status in _SKIP_STATUSES:
        return

    current = (getattr(member, "tag", None) or "").strip()
    if current and current not in GC.GURO_TAGS:
        return  # участник сам выставил себе тег вручную — не перетираем

    target = target_tag(storage, user_id)
    if current == target:
        return

    try:
        await bot.set_chat_member_tag(chat_id=chat_id, user_id=user_id, tag=target)
        logger.info(
            "guro_tags: тег обновлён chat_id=%s user_id=%s tag=%s reason=%s",
            chat_id, user_id, target, reason,
        )
    except TelegramError:
        logger.info(
            "guro_tags: не удалось выставить тег chat_id=%s user_id=%s reason=%s",
            chat_id, user_id, reason, exc_info=True,
        )


async def sync_member_tag_standalone(
    bot_token: str, chat_id: int, storage: GuroStorage, user_id: int, *, reason: str = ""
) -> None:
    """Для процессов без живого Application (guro_id_api.py, cron) — тот же
    разовый Bot(token), что уже используется в guro_id_api.py для уведомлений."""
    async with Bot(token=bot_token) as bot:
        await sync_member_tag(bot, chat_id, storage, user_id, reason=reason)


async def sync_all_members(
    bot: Bot,
    chat_id: int,
    storage: GuroStorage,
    user_ids: list[int],
    *,
    delay_seconds: float = 0.0,
    reason: str = "",
) -> None:
    """Массовый прогон (guro_tags_sync.py) — небольшая пауза между вызовами,
    чтобы не бить Telegram пачкой; объём здесь на порядки меньше полной
    группы (только те, кто коснулся GURO ID, см. list_guro_user_ids)."""
    for user_id in user_ids:
        await sync_member_tag(bot, chat_id, storage, user_id, reason=reason)
        if delay_seconds:
            await asyncio.sleep(delay_seconds)
