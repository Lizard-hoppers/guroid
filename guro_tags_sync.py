"""Периодический скрипт (systemd timer): актуализирует статус-теги GURO ID у
всех отслеживаемых участников — прежде всего понижает GURO ID PRO обратно до
GURO ID при истечении подписки (единственное событие без триггера в реальном
времени) и подчищает то, что не долетело сразу (сеть/лимиты). Отдельный
процесс от бота — тот же принцип изоляции, что у news_poster.py."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from telegram import Bot

import guro_tags as GT
from config import Settings
from guro_storage import GuroStorage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("guro_tags_sync")

# Пауза между вызовами set_chat_member_tag — объём здесь на порядки меньше
# полной группы (только те, кто хоть раз коснулся GURO ID).
DELAY_SECONDS = 0.2


async def main() -> None:
    settings = Settings.from_env()
    if not settings.community_chat_id:
        logger.info("COMMUNITY_CHAT_ID не задан, пропуск")
        return

    storage = GuroStorage(settings.database_path)
    user_ids = storage.list_guro_user_ids()
    logger.info("синхронизация тегов: %s пользователей", len(user_ids))

    async with Bot(token=settings.bot_token) as bot:
        await GT.sync_all_members(
            bot, settings.community_chat_id, storage, user_ids,
            delay_seconds=DELAY_SECONDS, reason="periodic_sync",
        )

    logger.info("готово")


if __name__ == "__main__":
    asyncio.run(main())
