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

# Сколько черновиков в день максимум показываем админам на выбор (не путать с
# темпом создания черновиков из RSS — тот не ограничен, лишние просто ждут
# своей очереди в news_pending_unnotified, старые первыми).
DAILY_ADMIN_LIMIT = 6


def _draft_kb(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Опубликовать", callback_data=f"news:pub:{draft_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"news:rej:{draft_id}"),
    ]])


async def _notify_admins(bot: Bot, settings: Settings, draft_id: int, text: str,
                          image_url: str | None, storage: Storage) -> None:
    """Шлёт черновик КАЖДОМУ админу и запоминает ID сообщения у каждого
    отдельно (news_admin_messages) — иначе при решении по черновику копия
    остаётся висеть с активными кнопками у всех, кроме того, кто её обработал."""
    for admin_id in settings.admin_ids:
        try:
            msg = await send_news_html(
                bot, admin_id, text, image_url, ParseMode.HTML,
                reply_markup=_draft_kb(draft_id),
            )
            storage.news_add_admin_msg(draft_id, admin_id, msg.message_id)
        except Exception:  # noqa: BLE001
            logger.exception("news: не удалось уведомить админа %s", admin_id)


async def _notify_up_to_quota(bot: Bot, settings: Settings, storage: Storage) -> int:
    """Дозаполняет дневную квоту показов админам из очереди непоказанных
    черновиков (старые первыми — честная очередь, а не самые свежие)."""
    remaining = DAILY_ADMIN_LIMIT - storage.news_notified_today_count()
    if remaining <= 0:
        return 0
    to_notify = storage.news_pending_unnotified(remaining)
    for draft in to_notify:
        await _notify_admins(bot, settings, draft["id"], draft["text"], draft["image_url"], storage)
        storage.news_mark_notified(draft["id"])
    return len(to_notify)


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
        created += 1
        logger.info("news: черновик #%s создан (%s), в очереди на показ", draft_id, item.source)

    notified = await _notify_up_to_quota(bot, settings, storage)
    logger.info(
        "news: готово, новых черновиков: %s, показано админам сейчас: %s, всего сегодня: %s/%s",
        created, notified, storage.news_notified_today_count(), DAILY_ADMIN_LIMIT,
    )
    storage.close()


if __name__ == "__main__":
    asyncio.run(main())
