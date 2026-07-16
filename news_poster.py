"""Периодический скрипт (systemd timer): RSS -> GPT-оформление -> черновик
админам на утверждение. Публикация в группу — по кнопке, её обрабатывает
CallbackQueryHandler в основном процессе бота (handlers/news.py), не этот скрипт.

Отдельный процесс от бота специально: сетевые вызовы к RSS/OpenAI не должны
блокировать или ронять анкету-бот (Clean & Live манифест — изоляция компонентов).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from config import Settings
from news_formatter import format_with_gpt, render_telegram_html, send_news_html
from news_sources import fetch_all
from storage import Storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("news_poster")


def _draft_kb(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Опубликовать", callback_data=f"news:pub:{draft_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"news:rej:{draft_id}"),
    ]])


async def _notify_admins(bot: Bot, settings: Settings, draft_id: int, text: str,
                          image_url: str | None, storage: Storage) -> None:
    admin_msg_id = None
    admin_chat_id = None
    for admin_id in settings.admin_ids:
        try:
            msg = await send_news_html(
                bot, admin_id, text, image_url, ParseMode.HTML,
                reply_markup=_draft_kb(draft_id),
            )
            admin_chat_id, admin_msg_id = admin_id, msg.message_id
        except Exception:  # noqa: BLE001
            logger.exception("news: не удалось уведомить админа %s", admin_id)
    if admin_msg_id:
        storage.news_set_admin_msg(draft_id, admin_chat_id, admin_msg_id)


async def main() -> None:
    settings = Settings.from_env()
    if not settings.news_enabled:
        logger.info("news: NEWS_ENABLED=false, выхожу")
        return
    if not settings.openai_api_key:
        logger.error("news: OPENAI_API_KEY не задан, выхожу")
        return

    storage = Storage(settings.database_path)
    bot = Bot(settings.bot_token)

    items = await fetch_all(limit_per_source=5)
    logger.info("news: получено %s элементов из RSS", len(items))

    created = 0
    for item in items:
        if storage.news_is_seen(item.guid):
            continue
        fn = await format_with_gpt(
            settings.openai_api_key, settings.openai_model,
            item.title, item.summary, item.source,
        )
        if fn is None:
            logger.warning("news: GPT не смог оформить %r, пропуск (без mark_seen — retry)", item.title)
            continue
        text = render_telegram_html(fn, item.source, item.url)
        draft_id = storage.news_save_draft(
            item.guid, item.source, item.url, item.title, text, item.image_url,
        )
        storage.news_mark_seen(item.guid, item.source, item.url)
        await _notify_admins(bot, settings, draft_id, text, item.image_url, storage)
        created += 1
        logger.info("news: черновик #%s создан (%s)", draft_id, item.source)

    logger.info("news: готово, новых черновиков: %s", created)
    storage.close()


if __name__ == "__main__":
    asyncio.run(main())
