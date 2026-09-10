"""Обслуживание платного входа в сообщество: напоминание за 2 дня и
выселение по истечении подписки (09.09.2026, systemd timer раз в сутки).

Владелец: «за два дня до окончания срока надо чтобы бот высылал
напоминание что заканчивается подписка на прибывание в комьюнити; если
человек не оплатил подписку его выкидывает с группы пока не оплатит; когда
оплатил снова получил ссылку на вход в комьюнити».

Отдельный процесс, а не job_queue внутри бота, — как guro_tags_sync.py:
падение или зависание обслуживания не должно ронять живого бота.

ПОРЯДОК ДЕЙСТВИЙ ВАЖЕН: сначала напоминания, потом выселения. У человека,
чей срок истекает прямо сегодня, оба условия могут сойтись в одном
запуске; напомнить и тут же выселить — грубо, но напомнить перед тем, как
выселять в следующий раз, — ровно то, о чём просил владелец.

КОГО НЕ ТРОГАЕМ: освобождённых от платного входа (признак community_
access_granted) — 1081 человек, вступивший до правила, и ручные выдачи
админа. Условие зашито в сами выборки, см. guro_storage.list_paywall_*.

Запуск вручную: .venv/bin/python guro_paywall_job.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from telegram import Bot

import community_access as CA
import ui
from config import Settings
from content import Content
from guro_storage import GuroStorage
from storage import Storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("guro_paywall_job")

REMIND_DAYS_BEFORE = 2

# Пауза между сообщениями/киками — тот же порядок, что у рассылок: лимит
# Telegram на исходящие ~30/с, а обслуживание никуда не спешит.
DELAY_SECONDS = 0.2


async def _remind(bot, storage: GuroStorage, content: Content, dry_run: bool) -> int:
    """Напоминание за REMIND_DAYS_BEFORE суток. Кнопки оплаты прикладываем
    прямо к нему: иначе человеку пришлось бы искать, где вообще платить."""
    sent = 0
    for row in storage.list_paywall_expiring(REMIND_DAYS_BEFORE):
        user_id, exp = row["user_id"], row["exp"]
        if dry_run:
            logger.info("напомнил бы %s (срок %s)", user_id, exp)
            sent += 1
            continue
        try:
            await bot.send_message(
                user_id, content.txt("paywall_expiring"),
                reply_markup=ui.paywall_kb(content),
            )
            sent += 1
        except Exception:  # noqa: BLE001
            # Заблокировал бота или удалил аккаунт — не повод останавливать
            # обслуживание остальных. Отметку всё равно ставим: повторять
            # доставку каждые сутки бессмысленно, срок один и тот же.
            logger.warning("не удалось напомнить %s", user_id, exc_info=True)
        storage.mark_paywall_reminded(user_id, exp)
        await asyncio.sleep(DELAY_SECONDS)
    return sent


async def _kick(bot, settings, storage: GuroStorage, content: Content, dry_run: bool) -> int:
    """Выселение по истечении подписки.

    Сначала пишем человеку, потом убираем из группы: обратный порядок
    оставил бы его гадать, за что его выкинули, — а сообщение объясняет,
    что доступ возвращается оплатой.
    """
    kicked = 0
    for row in storage.list_paywall_expired():
        user_id, exp = row["user_id"], row["exp"]
        if dry_run:
            logger.info("выселил бы %s (срок кончился %s)", user_id, exp)
            kicked += 1
            continue
        try:
            await bot.send_message(
                user_id, content.txt("paywall_expired"),
                reply_markup=ui.paywall_kb(content),
            )
        except Exception:  # noqa: BLE001
            logger.warning("не удалось предупредить %s о выселении", user_id, exc_info=True)
        if await CA.revoke_access(bot, settings, user_id):
            kicked += 1
        storage.mark_paywall_kicked(user_id, exp)
        await asyncio.sleep(DELAY_SECONDS)
    return kicked


async def main(dry_run: bool) -> None:
    settings = Settings.from_env()
    if not settings.community_chat_id:
        logger.info("COMMUNITY_CHAT_ID не задан, пропуск")
        return

    storage = GuroStorage(settings.database_path)
    content = Content(Storage(settings.database_path))

    async with Bot(token=settings.bot_token) as bot:
        reminded = await _remind(bot, storage, content, dry_run)
        kicked = await _kick(bot, settings, storage, content, dry_run)

    logger.info("готово: напоминаний %s, выселено %s%s",
                reminded, kicked, " (сухой прогон)" if dry_run else "")


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
