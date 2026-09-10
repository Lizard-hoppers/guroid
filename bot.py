"""Точка входа: Gambling Community Bot."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from telegram import MenuButtonWebApp, Update, WebAppInfo
from telegram.ext import Application, ContextTypes, PersistenceInput, PicklePersistence

from config import Settings
from content import Content
from google_sheets_sync import SheetSync
from guro_storage import GuroStorage
from handlers import (
    build_admin_cms,
    build_admin_handlers,
    build_admin_profiles_handlers,
    build_admin_users_handlers,
    build_conversation,
    build_gossip_handlers,
    build_group_captcha,
    build_guro_limits_handlers,
    build_guro_partnerships_handlers,
    build_guro_payments_handlers,
    build_news_handlers,
    build_paywall_handlers,
    build_referral_group_handlers,
    build_referral_handlers,
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


def _webapp_asset_version() -> str:
    """Cache-busting версия Menu Button (27.08.2026, багрепорт "не вижу новый
    дизайн") — Telegram WebView привязывает свой кеш к ТОЧНОЙ строке URL
    Menu Button, а она регистрируется один раз через set_chat_menu_button и
    после этого не меняется сама по себе между рестартами бота, даже если
    задеплоен новый webapp/dist — юзер видел старую версию, пока не менялся
    сам URL. Версия — хеш из имени собранного JS-файла (Vite меняет его при
    каждой пересборке), поэтому сама синхронизируется с тем, что реально
    задеплоено, без ручного бампа номера при каждом деплое фронтенда."""
    try:
        html = (Path(__file__).resolve().parent / "webapp" / "dist" / "index.html").read_text()
        m = re.search(r"assets/index-([A-Za-z0-9_-]+)\.js", html)
        return m.group(1) if m else "0"
    except OSError:
        return "0"


async def _post_init(app: Application) -> None:
    """Menu Button (кнопка слева от поля ввода в личке) открывает GURO ID
    Mini App напрямую — идемпотентно, безопасно вызывать при каждом старте.
    ?v=<hash> — см. _webapp_asset_version."""
    settings: Settings = app.bot_data["settings"]
    webapp_url = f"{settings.guro_id_webapp_url.rstrip('/')}/?v={_webapp_asset_version()}"
    try:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="GURO ID", web_app=WebAppInfo(url=webapp_url))
        )
    except Exception:  # noqa: BLE001
        logger.exception("guro_id: не удалось установить Menu Button")


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
        .post_init(_post_init)
        .build()
    )
    app.bot_data["settings"] = settings
    app.bot_data["storage"] = storage
    app.bot_data["sheet"] = sheet
    app.bot_data["content"] = Content(storage)
    # GURO ID: своё соединение к тому же sqlite-файлу (второй писатель — тот
    # же процесс, что и guro_id_api.py; WAL включается один раз в GuroStorage).
    app.bot_data["guro_storage"] = GuroStorage(settings.database_path)

    app.add_handler(build_admin_cms(settings.admin_ids))
    app.add_handler(build_conversation())
    for h in build_admin_handlers():
        app.add_handler(h)
    # Reply-клавиатура в группе (кнопка «Пригласить/Invite»): регистрируем
    # ДО гейта капчи, в том же group=1 — гейт слушает ЛЮБОЕ текстовое
    # сообщение в группе широким фильтром, и в пределах одной PTB-группы
    # выигрывает первый совпавший хендлер (порядок регистрации решает).
    for h in build_referral_group_handlers():
        app.add_handler(h, group=1)
    # Второй уровень: гейт группы — без анкеты мут (на входе и по первому
    # сообщению), после анкеты автоматический размут + приветствие.
    # group=1, чтобы MessageHandler гейта не конкурировал с ConversationHandler.
    if settings.captcha_enabled:
        for h in build_group_captcha():
            app.add_handler(h, group=1)
    # Быстрая карточка участника: админ форвардит в личку любое сообщение из
    # группы -> сразу открывается карточка (мут/бан), без захода в /admin.
    # group=1 — не конкурирует с ConversationHandler-ами (те же соображения).
    for h in build_admin_users_handlers():
        app.add_handler(h, group=1)
    # /guro_limit — оверрайд лимитов на аккаунт (ТЗ "Тарифы и лимиты",
    # раздел 3, 27.08.2026), тот же приём: обычный CommandHandler вне
    # ConversationHandler-состояний, group=1.
    for h in build_guro_limits_handlers(settings.admin_ids):
        app.add_handler(h, group=1)
    # Кнопки карточки анкеты (contact/unmute) — тоже вне ConversationHandler,
    # чтобы работали при открытии карточки по deep-link (?start=p_<id>).
    for h in build_admin_profiles_handlers():
        app.add_handler(h, group=1)
    # Новости индустрии: кнопки шлёт отдельный процесс news_poster.py (cron),
    # а публикует/отклоняет — вот этот хендлер (только он слушает getUpdates).
    for h in build_news_handlers():
        app.add_handler(h)
    # Сплетни/инсайды от участников: /gossip в личке -> GPT -> модерация ->
    # публикация в тот же чат, что и новости.
    for h in build_gossip_handlers():
        app.add_handler(h)
    # Реф-система: /invite в личке + кнопка «Получить реф-ссылку» в панели группы.
    for h in build_referral_handlers():
        app.add_handler(h)
    # GURO ID: кнопки Подтвердить/Отклонить под уведомлением о партнёрстве
    # (уведомление шлёт guro_id_api.py) + оплата подписки через Telegram Stars.
    for h in build_guro_partnerships_handlers():
        app.add_handler(h)
    for h in build_guro_payments_handlers():
        app.add_handler(h)
    # Платный вход в сообщество (09.09.2026): кнопки под экраном оплаты,
    # который показывается сразу после анкеты. Вне ConversationHandler —
    # к моменту нажатия разговор уже завершён (flow.py чистит user_data),
    # а сообщение с кнопками должно работать и через неделю.
    for h in build_paywall_handlers():
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
