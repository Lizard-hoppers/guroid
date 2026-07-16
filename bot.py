"""Точка входа: Gambling Community Bot."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, ContextTypes, PersistenceInput, PicklePersistence

from config import Settings
from content import Content
from google_sheets_sync import SheetSync
from handlers import (
    build_admin_cms,
    build_admin_handlers,
    build_conversation,
    build_gossip_handlers,
    build_group_captcha,
    build_news_handlers,
)
from storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("gambling_community_bot")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error", exc_info=context.error)


def main() -> None:
    settings = Settings.from_env()
    storage = Storage(settings.database_path)
    sheet = SheetSync(settings)

    # Персистентность: состояние диалогов и user_data переживают перезапуск.
    # bot_data исключаем — там runtime-объекты (storage/sheet/content), они не
    # сериализуются и пересоздаются при старте.
    persistence = PicklePersistence(
        filepath=str(settings.base_dir / "bot_persistence.pkl"),
        store_data=PersistenceInput(
            bot_data=False, chat_data=True, user_data=True, callback_data=False
        ),
    )

    app = (
        Application.builder()
        .token(settings.bot_token)
        .persistence(persistence)
        .build()
    )
    app.bot_data["settings"] = settings
    app.bot_data["storage"] = storage
    app.bot_data["sheet"] = sheet
    app.bot_data["content"] = Content(storage)

    app.add_handler(build_admin_cms())
    app.add_handler(build_conversation())
    for h in build_admin_handlers():
        app.add_handler(h)
    # Второй уровень: гейт группы — без анкеты мут (на входе и по первому
    # сообщению), после анкеты автоматический размут + приветствие.
    # group=1, чтобы MessageHandler гейта не конкурировал с ConversationHandler.
    if settings.captcha_enabled:
        for h in build_group_captcha():
            app.add_handler(h, group=1)
    # Новости индустрии: кнопки шлёт отдельный процесс news_poster.py (cron),
    # а публикует/отклоняет — вот этот хендлер (только он слушает getUpdates).
    for h in build_news_handlers():
        app.add_handler(h)
    # Сплетни/инсайды от участников: /gossip в личке -> GPT -> модерация ->
    # публикация в тот же чат, что и новости.
    for h in build_gossip_handlers():
        app.add_handler(h)
    app.add_error_handler(on_error)

    logger.info(
        "Bot starting. DB=%s sheets_enabled=%s invite=%s admins=%s captcha=%s groups=%s",
        settings.database_path,
        sheet.enabled,
        settings.community_invite_url,
        settings.admin_ids,
        settings.captcha_enabled,
        settings.captcha_group_ids or "all",
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
