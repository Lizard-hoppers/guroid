"""Админ-раздел «Контент»: визуальное редактирование текстов и подписей кнопок.

Паттерн как в Taki Вместе: эффективное значение = override из БД → дефолт из кода.
Правки применяются на лету (без рестарта). Доступ — только ADMIN_IDS.
"""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import constants as C
import logic
import ui
from handlers import admin_broadcast as BC
from handlers import admin_guro as GURO
from handlers import admin_log as LOG
from handlers import admin_profiles as PF
from handlers import admin_ui
from handlers import admin_users as US
from handlers import group_captcha as gate

logger = logging.getLogger(__name__)

BROWSE = admin_ui.BROWSE
WAIT_TEXT, WAIT_MEDIA, WAIT_GM_TEXT, WAIT_GM_EMOJI = range(1, 5)
# Состояния разделов «Анкеты»/«Рассылка» — собственные строковые константы в
# их модулях (PF.WAIT_SEARCH, BC.WAIT_*), чтобы не заводить циклический импорт
# с admin_cms.py; ConversationHandler допускает произвольные hashable-ключи.

_MEDIA_LABELS = {"animation": "GIF/анимация", "photo": "фото", "video": "видео"}


# --- helpers --------------------------------------------------------------

def _is_admin(update: Update, context) -> bool:
    settings = context.bot_data["settings"]
    u = update.effective_user
    return bool(u and settings.is_admin(u.id))


def _content(context):
    return context.bot_data["content"]


def _short(s: str, n: int = 40) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


async def _store(context, msg) -> None:
    await admin_ui.store_screen(context, msg)


async def _edit(context, text: str, kb=None) -> bool:
    return await admin_ui.edit_screen(context, text, kb)


# --- keyboards ------------------------------------------------------------

def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Тексты", callback_data="acms_texts")],
        [InlineKeyboardButton("🎛 Кнопки", callback_data="acms_btns")],
        [InlineKeyboardButton("🖼 Медиа", callback_data="acms_media")],
        [InlineKeyboardButton("🔗 Меню группы", callback_data="acms_gm")],
        [InlineKeyboardButton("‹ Панель управления", callback_data="acms_home")],
    ])


def _dashboard_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Анкеты", callback_data="acms_pf"),
         InlineKeyboardButton("👤 Пользователи", callback_data="acms_users")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="acms_bc"),
         InlineKeyboardButton("📝 Журнал", callback_data="acms_log")],
        [InlineKeyboardButton("⚙️ Режимы", callback_data="acms_modes"),
         InlineKeyboardButton("🎛 Контент", callback_data="acms_menu")],
        [InlineKeyboardButton("🪪 GURO ID", callback_data="acms_guro")],
        [InlineKeyboardButton("✖ Выход", callback_data="acms_exit")],
    ])


def _media_kb(context) -> InlineKeyboardMarkup:
    have = context.bot_data["storage"].media_keys()
    rows = []
    for key, label in C.TEXT_CATALOG:
        mark = "✅ " if key in have else ""
        rows.append([InlineKeyboardButton(f"{mark}{label}", callback_data=f"acms_em:{key}")])
    rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_menu")])
    return InlineKeyboardMarkup(rows)


def _texts_kb(context) -> InlineKeyboardMarkup:
    over = context.bot_data["storage"].overridden_texts()
    rows = []
    for key, label in C.TEXT_CATALOG:
        mark = "✅ " if key in over else ""
        rows.append([InlineKeyboardButton(f"{mark}{label}", callback_data=f"acms_et:{key}")])
    rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_menu")])
    return InlineKeyboardMarkup(rows)


def _btn_cats_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(title, callback_data=f"acms_btncat:{i}")]
        for i, (title, _keys) in enumerate(C.BUTTON_CATALOG)
    ]
    rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_menu")])
    return InlineKeyboardMarkup(rows)


def _btn_group_kb(context, cat: int) -> InlineKeyboardMarkup:
    c = _content(context)
    over = context.bot_data["storage"].overridden_buttons()
    _title, keys = C.BUTTON_CATALOG[cat]
    rows = []
    for key in keys:
        mark = "✅ " if key in over else ""
        rows.append([InlineKeyboardButton(f"{mark}{_short(c.btn(key))}", callback_data=f"acms_eb:{key}")])
    rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_btns")])
    return InlineKeyboardMarkup(rows)


def _edit_kb(target_kind: str, overridden: bool, back_cb: str) -> InlineKeyboardMarkup:
    rows = []
    if overridden:
        rows.append([InlineKeyboardButton("♻ Сбросить к умолчанию", callback_data="acms_reset")])
    rows.append([InlineKeyboardButton("‹ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)


# --- screens --------------------------------------------------------------

async def _show_dashboard(context) -> int:
    storage = context.bot_data["storage"]
    settings = context.bot_data["settings"]
    gate_on = storage.get_flag("gate_enabled", settings.captcha_enabled)
    greet_on = storage.get_flag("greeting_enabled", True)
    gossip_on = storage.get_flag("gossip_enabled", True)
    text = (
        "🛠 <b>Админ-панель</b>\n\n"
        f"Анкет всего: <b>{storage.count()}</b> (+{storage.count_since(24)} за 24ч)\n"
        f"Сплетни на модерации: <b>{storage.gossip_pending_count()}</b>\n"
        f"Новости на модерации: <b>{storage.news_pending_count()}</b>\n\n"
        f"Режимы: гейт {'🟢' if gate_on else '⚪'} · приветствие {'🟢' if greet_on else '⚪'} · "
        f"сплетни {'🟢' if gossip_on else '⚪'}"
    )
    await _edit(context, text, _dashboard_kb())
    return BROWSE


async def _show_menu(context) -> int:
    await _edit(
        context,
        "🎨 <b>Управление контентом</b>\n\n"
        "Кастомизация бота без доступа к серверу. Изменения применяются сразу.\n\n"
        "• <b>Тексты</b> — сообщения блоков 1–7.\n"
        "• <b>Кнопки</b> — подписи кнопок (основные, вертикали, грейды, инвестор).\n"
        "• <b>Медиа</b> — GIF/фото/видео на экранах (показывается как подпись к медиа).",
        _menu_kb(),
    )
    return BROWSE


async def _show_text_edit(context, key: str) -> int:
    storage = context.bot_data["storage"]
    label = dict(C.TEXT_CATALOG).get(key, key)
    override = storage.get_text_override(key)
    effective = override if override else C.TEXT_DEFAULTS.get(key, "(не задано)")
    src = "изменён в CMS ✅" if override else "по умолчанию"
    context.user_data["cms_target"] = ("txt", key)
    header = (
        f"📝 <b>{logic.html_escape(label)}</b>\n"
        f"<i>Сейчас ({src}) — как увидит пользователь:</i>\n\n"
    )
    tail = (
        "\n\n✍️ Пришлите новый текст сообщением, чтобы заменить "
        "(HTML и &lt;tg-emoji&gt; поддерживаются)."
    )
    kb = _edit_kb("txt", bool(override), "acms_texts")
    # живой рендер: жирный/премиум-эмодзи видно как в боте; битый HTML — исходником
    if not await _edit(context, header + effective + tail, kb):
        await _edit(context, header + logic.html_escape(effective) + tail, kb)
    return WAIT_TEXT


async def _show_btn_edit(context, key: str) -> int:
    storage = context.bot_data["storage"]
    c = _content(context)
    override = storage.get_button_override(key)
    effective = c.btn(key)
    default = C.BUTTON_DEFAULTS.get(key, key)
    src = "изменена в CMS ✅" if override else "по умолчанию"
    context.user_data["cms_target"] = ("btn", key)
    cat = context.user_data.get("cms_cat", 0)
    await _edit(
        context,
        f"🎛 <b>Кнопка</b> <code>{key}</code>\n"
        f"<i>Подпись ({src}):</i> {logic.html_escape(effective)}\n"
        f"<i>Умолчание:</i> {logic.html_escape(default)}\n\n"
        "✍️ Пришлите новую подпись сообщением, чтобы заменить.",
        _edit_kb("btn", bool(override), f"acms_btncat:{cat}"),
    )
    return WAIT_TEXT


async def _show_media_edit(context, key: str) -> int:
    storage = context.bot_data["storage"]
    label = dict(C.TEXT_CATALOG).get(key, key)
    media = storage.get_media(key)
    context.user_data["cms_target"] = ("media", key)
    if media:
        _fid, mtype = media
        status = f"задано ✅ ({_MEDIA_LABELS.get(mtype, mtype)})"
    else:
        status = "не задано"
    await _edit(
        context,
        f"🖼 <b>Медиа экрана:</b> {logic.html_escape(label)}\n"
        f"<i>Сейчас:</i> {status}\n\n"
        "📎 Пришлите <b>GIF</b>, фото или видео сообщением, чтобы установить его на этот экран.\n"
        "Текст экрана станет подписью к медиа.",
        _media_edit_kb(bool(media)),
    )
    return WAIT_MEDIA


def _media_edit_kb(have: bool) -> InlineKeyboardMarkup:
    rows = []
    if have:
        rows.append([InlineKeyboardButton("🗑 Удалить медиа", callback_data="acms_reset")])
    rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_media")])
    return InlineKeyboardMarkup(rows)


# --- handlers -------------------------------------------------------------

async def _redirect_if_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Админ-панель не должна разворачиваться в группе на виду у всех. Тот же
    singleton-слот "start_redirect", что и у flow.start() — оба редиректа
    взаимоисключающие (один физический /start обрабатывает либо этот
    ConversationHandler, либо gambling_form, не оба). True — редирект
    отправлен, вызывающий код должен сразу вернуть ConversationHandler.END."""
    if update.effective_chat.type == "private":
        return False
    chat_id = update.effective_chat.id
    await gate.post_singleton_group_message(
        context, chat_id, "start_redirect",
        lambda: context.bot.send_message(
            chat_id,
            "Админ-панель открывается только в личном сообщении с ботом — нажмите кнопку ниже 👇",
            reply_markup=InlineKeyboardMarkup([[ui.link_button(
                "➡️ Перейти к боту", f"https://t.me/{context.bot.username}", style="primary",
            )]]),
        ),
    )
    return True


async def admin_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    try:
        await update.message.delete()  # Clean Chat: убираем /admin
    except Exception:  # noqa: BLE001
        pass
    if await _redirect_if_group(update, context):
        return ConversationHandler.END
    if not _is_admin(update, context):
        await context.bot.send_message(chat_id, "Команда доступна только администратору.")
        return ConversationHandler.END
    msg = await context.bot.send_message(chat_id, "…")
    await _store(context, msg)
    return await _show_dashboard(context)


async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/start для админа — ВТОРОЙ entry_point ЭТОГО ConversationHandler (не
    admin_open внутри flow.start()!). Это принципиально: только через entry_point
    самого gambling_admin_cms (с allow_reentry=True) PTB по-настоящему проставляет
    conversation state. Раньше flow.start() вызывал admin_open() напрямую в обход
    диспетчера — рендерилась панель, но состояние диалога не проставлялось, и
    если у админа не было уже АКТИВНОЙ сессии /admin (например, только что вышел
    через «✖ Выход», который явно завершает диалог) — все кнопки дашборда молча
    переставали отвечать (баг найден 20.07.2026 — «зависание админки»)."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    try:
        await update.message.delete()  # Clean Chat: убираем /start
    except Exception:  # noqa: BLE001
        pass
    if await _redirect_if_group(update, context):
        return ConversationHandler.END
    await gate.delete_gate_prompts(context, user.id)

    # deep-link из списка «Анкеты»/«Пользователи» (клик по ID) -> сразу карточка
    args = context.args or []
    payload = args[0] if args else ""
    target = payload.split("_", 1)[1] if "_" in payload else ""
    if target.isdigit() and (payload.startswith("u_") or payload.startswith("p_")):
        await admin_ui.delete_previous_screen(context)
        if payload.startswith("u_"):
            await US.send_card_message(context, chat_id, int(target))
        else:
            await PF.send_card_message(context, chat_id, int(target))
        return ConversationHandler.END

    await admin_ui.delete_previous_screen(context)
    msg = await context.bot.send_message(chat_id, "…")
    await _store(context, msg)
    return await _show_dashboard(context)


async def nav_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _show_dashboard(context)


async def nav_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _show_menu(context)


async def nav_texts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await _edit(context, "📝 <b>Тексты</b>\n\nВыберите сообщение (✅ — изменено):", _texts_kb(context))
    return BROWSE


async def nav_btns(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await _edit(context, "🎛 <b>Кнопки</b>\n\nВыберите раздел:", _btn_cats_kb())
    return BROWSE


async def nav_btncat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    cat = int(update.callback_query.data.split(":", 1)[1])
    context.user_data["cms_cat"] = cat
    title = C.BUTTON_CATALOG[cat][0]
    await _edit(context, f"🎛 <b>{title}</b>\n\nВыберите кнопку (✅ — изменена):", _btn_group_kb(context, cat))
    return BROWSE


async def nav_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await _edit(context, "🖼 <b>Медиа</b>\n\nВыберите экран (✅ — медиа задано):", _media_kb(context))
    return BROWSE


def _mode_dot(on: bool) -> str:
    return "🟢" if on else "🔴"


def _modes_kb(context) -> InlineKeyboardMarkup:
    storage = context.bot_data["storage"]
    settings = context.bot_data["settings"]
    gate_on = storage.get_flag("gate_enabled", settings.captcha_enabled)
    greet_on = storage.get_flag("greeting_enabled", True)
    gossip_on = storage.get_flag("gossip_enabled", True)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{_mode_dot(gate_on)} 🔒 Гейт (мут без анкеты) · {'вкл' if gate_on else 'выкл'}",
            callback_data="acms_tgl:gate")],
        [InlineKeyboardButton(
            f"{_mode_dot(greet_on)} 👋 Приветствие новичкам · {'вкл' if greet_on else 'выкл'}",
            callback_data="acms_tgl:greet")],
        [InlineKeyboardButton(
            f"{_mode_dot(gossip_on)} \U0001f5e3 Сплетни от участников · {'вкл' if gossip_on else 'выкл'}",
            callback_data="acms_tgl:gossip")],
        [InlineKeyboardButton("‹ Панель управления", callback_data="acms_home")],
    ])


_MODES_TEXT = (
    "⚙️ <b>Режимы</b>\n\n"
    "🔒 <b>Гейт</b> · вкл — писать в группе могут только прошедшие анкету, "
    "остальных бот мутит (на входе и по первому сообщению).\n"
    "· выкл — писать могут все; при выключении бот размучивает всех, кого "
    "замутил, и подчищает просьбы «пройди анкету».\n\n"
    "👋 <b>Приветствие</b> — сообщение с полезными ссылками новичку при входе "
    "в группу.\n\n"
    "\U0001f5e3 <b>Сплетни</b> · вкл — прошедшие анкету могут прислать боту "
    "инсайд через /gossip, бот оформит через ИИ и отправит вам на "
    "модерацию.\n· выкл — бот сразу отвечает, что приём временно закрыт.\n\n"
    "Нажатие на кнопку переключает режим сразу."
)


async def nav_modes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await _edit(context, _MODES_TEXT, _modes_kb(context))
    return BROWSE


async def toggle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    which = q.data.split(":", 1)[1]
    storage = context.bot_data["storage"]
    settings = context.bot_data["settings"]
    if which == "gate":
        new = not storage.get_flag("gate_enabled", settings.captcha_enabled)
        storage.set_flag("gate_enabled", new)
        storage.log_action(update.effective_user.id, "gate_toggle", "вкл" if new else "выкл")
        if new:
            await q.answer("Гейт включён: без анкеты — мут")
        else:
            muted = len(storage.all_group_mutes())
            await q.answer(f"Гейт выключен. Размучиваю замученных: {muted}")
            if muted:
                # НЕ context.application.create_task — PTB ждёт такие задачи
                # при остановке (стоп/деплой висит, пока не размутит всех —
                # для большой группы это могло бы занять минуты). Настоящий
                # fire-and-forget, см. group_captcha.spawn_background.
                gate.spawn_background(context, gate.gate_unmute_all(context))
    elif which == "greet":
        new = not storage.get_flag("greeting_enabled", True)
        storage.set_flag("greeting_enabled", new)
        storage.log_action(update.effective_user.id, "greeting_toggle", "вкл" if new else "выкл")
        await q.answer("Приветствие включено" if new else "Приветствие выключено")
    else:
        new = not storage.get_flag("gossip_enabled", True)
        storage.set_flag("gossip_enabled", new)
        storage.log_action(update.effective_user.id, "gossip_toggle", "вкл" if new else "выкл")
        await q.answer("Приём сплетен включён" if new else "Приём сплетен выключен")
    await _edit(context, _MODES_TEXT, _modes_kb(context))
    return BROWSE


async def edit_media_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    key = update.callback_query.data.split(":", 1)[1]
    return await _show_media_edit(context, key)


async def save_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kind, key = context.user_data.get("cms_target", (None, None))
    msg = update.message
    file_id = mtype = None
    if msg.animation:
        file_id, mtype = msg.animation.file_id, "animation"
    elif msg.photo:
        file_id, mtype = msg.photo[-1].file_id, "photo"
    elif msg.video:
        file_id, mtype = msg.video.file_id, "video"
    elif msg.document and (msg.document.mime_type or "").startswith(("image/", "video/")):
        file_id = msg.document.file_id
        mtype = "animation" if "gif" in (msg.document.mime_type or "") else "photo"
    try:
        await msg.delete()
    except Exception:  # noqa: BLE001
        pass
    if not file_id or kind != "media":
        return await _show_media_edit(context, key) if key else await _show_menu(context)
    context.bot_data["storage"].set_media(key, file_id, mtype)
    return await _show_media_edit(context, key)


async def edit_text_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    key = update.callback_query.data.split(":", 1)[1]
    return await _show_text_edit(context, key)


async def edit_btn_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    key = update.callback_query.data.split(":", 1)[1]
    return await _show_btn_edit(context, key)


async def save_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kind, key = context.user_data.get("cms_target", (None, None))
    new_value = update.message.text or ""
    try:
        await update.message.delete()
    except Exception:  # noqa: BLE001
        pass
    if not kind:
        return await _show_menu(context)
    storage = context.bot_data["storage"]
    if kind == "txt":
        storage.set_text_override(key, new_value)
        return await _show_text_edit(context, key)
    storage.set_button_override(key, new_value.strip())
    return await _show_btn_edit(context, key)


async def reset_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kind, key = context.user_data.get("cms_target", (None, None))
    storage = context.bot_data["storage"]
    if kind == "txt":
        await update.callback_query.answer("Сброшено к умолчанию")
        storage.reset_text(key)
        return await _show_text_edit(context, key)
    if kind == "btn":
        await update.callback_query.answer("Сброшено к умолчанию")
        storage.reset_button(key)
        return await _show_btn_edit(context, key)
    if kind == "media":
        await update.callback_query.answer("Медиа удалено")
        storage.reset_media(key)
        return await _show_media_edit(context, key)
    await update.callback_query.answer()
    return await _show_menu(context)


async def admin_exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    try:
        await context.bot.delete_message(
            chat_id=context.user_data["adm_chat"],
            message_id=context.user_data["adm_mid"],
        )
    except Exception:  # noqa: BLE001
        pass
    context.user_data.clear()
    return ConversationHandler.END


# --- раздел «Меню группы» (кнопки-ссылки после капчи) --------------------

def _gm_list_kb(context) -> InlineKeyboardMarkup:
    storage = context.bot_data["storage"]
    rows = []
    dots = {"default": "⚪", "primary": "🔵", "success": "🟢", "danger": "🔴"}
    for b in storage.menu_buttons():
        mark = "" if b["enabled"] else "🚫 "
        dot = dots.get(b["style"], "🎨")  # 🎨 = авто-шахматный
        star = "⭐" if b["emoji_id"] else ""
        label = b["label"] or b["url"] or f"slot {b['slot']}"
        rows.append([InlineKeyboardButton(f"{mark}{dot}{star} {_short(label, 28)}",
                                          callback_data=f"acms_gmbtn:{b['slot']}")])
    rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_menu")])
    return InlineKeyboardMarkup(rows)


def _gm_btn_kb(b, preview_style: str | None = None) -> InlineKeyboardMarkup:
    slot = b["slot"]
    rows = []
    if (b["url"] or "").strip():
        # живой предпросмотр: кнопка ровно в том виде (цвет/иконка/текст), как в группе
        rows.append([ui.link_button(b["label"] or b["url"], b["url"],
                                    preview_style, b["emoji_id"])])
    rows += [
        [InlineKeyboardButton("✏️ Текст", callback_data=f"acms_gmlabel:{slot}")],
        [InlineKeyboardButton("🔗 Ссылка", callback_data=f"acms_gmurl:{slot}")],
        [InlineKeyboardButton("🎨 Цвет", callback_data=f"acms_gmcolor:{slot}")],
        [InlineKeyboardButton("⭐ Премиум-эмодзи", callback_data=f"acms_gmemoji:{slot}")],
        [InlineKeyboardButton("🚫 Выключить" if b["enabled"] else "✅ Включить",
                              callback_data=f"acms_gmtoggle:{slot}")],
        [InlineKeyboardButton("♻ Сбросить к умолчанию", callback_data=f"acms_gmreset:{slot}")],
        [InlineKeyboardButton("‹ Назад", callback_data="acms_gm")],
    ]
    return InlineKeyboardMarkup(rows)


def _gm_color_kb(slot: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(lbl, callback_data=f"acms_gmstyle:{slot}:{key}")]
            for key, lbl in C.MENU_STYLE_LABELS.items()]
    rows.append([InlineKeyboardButton("‹ Назад", callback_data=f"acms_gmbtn:{slot}")])
    return InlineKeyboardMarkup(rows)


def _gm_back_kb(slot: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("‹ Назад", callback_data=f"acms_gmbtn:{slot}")]]
    )


async def nav_groupmenu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await _edit(
        context,
        "🔗 <b>Меню группы</b>\n\nКнопки-ссылки в приветствии группы. "
        "Цвет: 🎨 — авто-шахматный (синий/зелёный), ⭐ — задана премиум-иконка.\n\n"
        "Выберите кнопку (🚫 — выключена):",
        _gm_list_kb(context),
    )
    return BROWSE


async def _show_gm_button(context, slot: int) -> int:
    storage = context.bot_data["storage"]
    b = storage.get_menu_button(slot)
    if not b:
        return await _show_menu(context)
    # реальный цвет с учётом авто-шахматного дефолта по позиции в панели
    enabled = [x for x in storage.menu_buttons(only_enabled=True) if (x["url"] or "").strip()]
    pos = next((i for i, x in enumerate(enabled) if x["slot"] == slot), None)
    chess = "primary"
    if pos is not None:
        row, col = divmod(pos, 2)
        chess = "primary" if (row + col) % 2 == 0 else "success"
    if b["style"]:
        color = C.MENU_STYLE_LABELS.get(b["style"], b["style"])
        preview_style = b["style"]
    else:
        color = f"авто-шахматный → {C.MENU_STYLE_LABELS.get(chess)}"
        preview_style = chess
    emoji = b["emoji_id"]
    if emoji and str(emoji).isdigit():
        emoji_disp = (f'<tg-emoji emoji-id="{emoji}">✨</tg-emoji> '
                      f"<code>{logic.html_escape(str(emoji))}</code>")
    elif emoji:
        emoji_disp = f"<code>{logic.html_escape(str(emoji))}</code>"
    else:
        emoji_disp = "—"
    state = "включена ✅" if b["enabled"] else "выключена 🚫"
    await _edit(
        context,
        f"🔗 <b>Кнопка панели</b>\n"
        f"<i>Предпросмотр (первая кнопка ниже — как в группе):</i>\n"
        f"<i>Текст:</i> {logic.html_escape(b['label'])}\n"
        f"<i>Ссылка:</i> {logic.html_escape(b['url'])}\n"
        f"<i>Цвет:</i> {color}\n"
        f"<i>Премиум-эмодзи:</i> {emoji_disp}\n"
        f"<i>Статус:</i> {state}",
        _gm_btn_kb(b, preview_style),
    )
    return BROWSE


async def gm_open_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    slot = int(update.callback_query.data.split(":", 1)[1])
    return await _show_gm_button(context, slot)


async def gm_edit_label(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    slot = int(update.callback_query.data.split(":", 1)[1])
    context.user_data["cms_target"] = ("gm_label", slot)
    await _edit(context, "✍️ Пришлите новый <b>текст</b> кнопки.", _gm_back_kb(slot))
    return WAIT_GM_TEXT


async def gm_edit_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    slot = int(update.callback_query.data.split(":", 1)[1])
    context.user_data["cms_target"] = ("gm_url", slot)
    await _edit(context, "✍️ Пришлите новую <b>ссылку</b> (https://t.me/...).", _gm_back_kb(slot))
    return WAIT_GM_TEXT


async def gm_edit_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    slot = int(update.callback_query.data.split(":", 1)[1])
    context.user_data["cms_target"] = ("gm_emoji", slot)
    await _edit(
        context,
        "⭐ Пришлите <b>премиум-эмодзи</b> (просто отправьте его сообщением) — бот возьмёт "
        "его id. Можно прислать id числом. Чтобы убрать иконку — отправьте «<code>-</code>».",
        _gm_back_kb(slot),
    )
    return WAIT_GM_EMOJI


async def gm_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    slot = int(update.callback_query.data.split(":", 1)[1])
    await _edit(context, "🎨 Выберите цвет кнопки:", _gm_color_kb(slot))
    return BROWSE


async def gm_set_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer("Цвет обновлён")
    _, slot_s, style = update.callback_query.data.split(":")
    storage = context.bot_data["storage"]
    storage.update_menu_button(int(slot_s), style=None if style == "default" else style)
    return await _show_gm_button(context, int(slot_s))


async def gm_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    slot = int(update.callback_query.data.split(":", 1)[1])
    storage = context.bot_data["storage"]
    b = storage.get_menu_button(slot)
    if b:
        storage.update_menu_button(slot, enabled=0 if b["enabled"] else 1)
    return await _show_gm_button(context, slot)


async def gm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer("Сброшено к умолчанию")
    slot = int(update.callback_query.data.split(":", 1)[1])
    context.bot_data["storage"].reset_menu_button(slot)
    return await _show_gm_button(context, slot)


async def gm_save_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kind, slot = context.user_data.get("cms_target", (None, None))
    val = (update.message.text or "").strip()
    try:
        await update.message.delete()
    except Exception:  # noqa: BLE001
        pass
    storage = context.bot_data["storage"]
    if val and kind == "gm_label":
        storage.update_menu_button(slot, label=val)
    elif val and kind == "gm_url":
        storage.update_menu_button(slot, url=val)
    if slot is None:
        return await _show_menu(context)
    return await _show_gm_button(context, slot)


async def gm_save_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kind, slot = context.user_data.get("cms_target", (None, None))
    msg = update.message
    emoji_id = None
    for e in (getattr(msg, "entities", None) or []):
        if getattr(e, "type", None) == "custom_emoji" and getattr(e, "custom_emoji_id", None):
            emoji_id = e.custom_emoji_id
            break
    text = (msg.text or "").strip()
    try:
        await msg.delete()
    except Exception:  # noqa: BLE001
        pass
    storage = context.bot_data["storage"]
    if kind == "gm_emoji" and slot is not None:
        if emoji_id:
            storage.update_menu_button(slot, emoji_id=str(emoji_id))
        elif text == "-":
            storage.update_menu_button(slot, emoji_id=None)
        elif text.isdigit():
            storage.update_menu_button(slot, emoji_id=text)
    if slot is None:
        return await _show_menu(context)
    return await _show_gm_button(context, slot)


def build_admin_cms(admin_ids: tuple[int, ...] = ()) -> ConversationHandler:
    nav = [
        CallbackQueryHandler(nav_home, pattern=r"^acms_home$"),
        CallbackQueryHandler(nav_menu, pattern=r"^acms_menu$"),
        CallbackQueryHandler(nav_texts, pattern=r"^acms_texts$"),
        CallbackQueryHandler(nav_btns, pattern=r"^acms_btns$"),
        CallbackQueryHandler(nav_media, pattern=r"^acms_media$"),
        CallbackQueryHandler(nav_btncat, pattern=r"^acms_btncat:\d+$"),
        CallbackQueryHandler(edit_text_start, pattern=r"^acms_et:"),
        CallbackQueryHandler(edit_btn_start, pattern=r"^acms_eb:"),
        CallbackQueryHandler(edit_media_start, pattern=r"^acms_em:"),
        # раздел «Режимы» (тумблеры)
        CallbackQueryHandler(nav_modes, pattern=r"^acms_modes$"),
        CallbackQueryHandler(toggle_mode, pattern=r"^acms_tgl:(gate|greet|gossip)$"),
        # раздел «Меню группы»
        CallbackQueryHandler(nav_groupmenu, pattern=r"^acms_gm$"),
        CallbackQueryHandler(gm_open_button, pattern=r"^acms_gmbtn:\d+$"),
        CallbackQueryHandler(gm_edit_label, pattern=r"^acms_gmlabel:\d+$"),
        CallbackQueryHandler(gm_edit_url, pattern=r"^acms_gmurl:\d+$"),
        CallbackQueryHandler(gm_edit_emoji, pattern=r"^acms_gmemoji:\d+$"),
        CallbackQueryHandler(gm_color, pattern=r"^acms_gmcolor:\d+$"),
        CallbackQueryHandler(gm_set_style, pattern=r"^acms_gmstyle:\d+:(default|primary|success|danger)$"),
        CallbackQueryHandler(gm_toggle, pattern=r"^acms_gmtoggle:\d+$"),
        CallbackQueryHandler(gm_reset, pattern=r"^acms_gmreset:\d+$"),
        CallbackQueryHandler(admin_exit, pattern=r"^acms_exit$"),
        # раздел «Анкеты» (карточка: pf_open/pf_toggle_contact/pf_unmute — в
        # build_admin_profiles_handlers(), group=1, см. докстринг admin_profiles.py)
        CallbackQueryHandler(PF.nav_profiles, pattern=r"^acms_pf$"),
        CallbackQueryHandler(PF.pf_page, pattern=r"^acms_pf_list:\d+$"),
        CallbackQueryHandler(PF.pf_search_start, pattern=r"^acms_pf_search$"),
        # раздел «Пользователи» (карточка: usr_* — в build_admin_users_handlers(),
        # group=1, см. докстринг admin_users.py)
        CallbackQueryHandler(US.nav_users, pattern=r"^acms_users$"),
        CallbackQueryHandler(US.usr_list_page, pattern=r"^acms_users_p:\d+$"),
        # раздел «Рассылка» (Live Broadcast Builder)
        CallbackQueryHandler(BC.nav_broadcast, pattern=r"^acms_bc$"),
        CallbackQueryHandler(BC.bc_audience_all, pattern=r"^acms_bc_aud:all$"),
        CallbackQueryHandler(BC.bc_audience_vertical_menu, pattern=r"^acms_bc_aud:vertical$"),
        CallbackQueryHandler(BC.bc_audience_grade_menu, pattern=r"^acms_bc_aud:grade$"),
        CallbackQueryHandler(BC.bc_audience_country_menu, pattern=r"^acms_bc_aud:country$"),
        CallbackQueryHandler(BC.bc_pick_vertical, pattern=r"^acms_bc_vert:\d+$"),
        CallbackQueryHandler(BC.bc_pick_grade, pattern=r"^acms_bc_grade:\d+$"),
        CallbackQueryHandler(BC.bc_pick_country, pattern=r"^acms_bc_country:\d+$"),
        CallbackQueryHandler(BC.bc_pick_country_other, pattern=r"^acms_bc_country_other$"),
        CallbackQueryHandler(BC.bc_audience_count, pattern=r"^acms_bc_count$"),
        CallbackQueryHandler(BC.bc_add_item_start, pattern=r"^acms_bc_additem$"),
        CallbackQueryHandler(BC.bc_btn_choice, pattern=r"^acms_bc_btn:(yes|no)$"),
        CallbackQueryHandler(BC.bc_remove_last, pattern=r"^acms_bc_removelast$"),
        CallbackQueryHandler(BC.bc_send, pattern=r"^acms_bc_send$"),
        CallbackQueryHandler(BC.bc_cancel, pattern=r"^acms_bc_cancel$"),
        # раздел «Журнал»
        CallbackQueryHandler(LOG.nav_log, pattern=r"^acms_log$"),
        CallbackQueryHandler(LOG.log_page, pattern=r"^acms_log_p:\d+$"),
        # раздел «GURO ID» (статистика, read-only) — handlers/admin_guro.py
        CallbackQueryHandler(GURO.nav_guro, pattern=r"^acms_guro$"),
    ]
    media_filter = filters.ANIMATION | filters.PHOTO | filters.VIDEO | filters.Document.ALL
    return ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin_open),
            # /start для админа — тоже entry_point ЭТОГО ConversationHandler
            # (allow_reentry=True ниже гарантирует, что он сработает даже если
            # у админа уже была/не была активная сессия — см. докстринг admin_start)
            *([CommandHandler("start", admin_start, filters=filters.User(user_id=list(admin_ids)))]
              if admin_ids else []),
        ],
        states={
            BROWSE: nav,
            WAIT_TEXT: [
                CallbackQueryHandler(reset_value, pattern=r"^acms_reset$"),
                *nav,
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_value),
            ],
            WAIT_MEDIA: [
                CallbackQueryHandler(reset_value, pattern=r"^acms_reset$"),
                *nav,
                MessageHandler(media_filter, save_media),
            ],
            WAIT_GM_TEXT: [
                *nav,
                MessageHandler(filters.TEXT & ~filters.COMMAND, gm_save_text),
            ],
            WAIT_GM_EMOJI: [
                *nav,
                MessageHandler(filters.TEXT & ~filters.COMMAND, gm_save_emoji),
            ],
            PF.WAIT_SEARCH: [
                *nav,
                MessageHandler(filters.TEXT & ~filters.COMMAND, PF.pf_search_text),
            ],
            US.WAIT_LOOKUP: [
                *nav,
                MessageHandler(filters.TEXT & ~filters.COMMAND, US.lookup_text),
            ],
            BC.WAIT_TEXT: [
                *nav,
                MessageHandler(filters.TEXT & ~filters.COMMAND, BC.bc_item_text),
            ],
            BC.WAIT_BTN_LABEL: [
                *nav,
                MessageHandler(filters.TEXT & ~filters.COMMAND, BC.bc_btn_label),
            ],
            BC.WAIT_BTN_URL: [
                *nav,
                MessageHandler(filters.TEXT & ~filters.COMMAND, BC.bc_btn_url),
            ],
        },
        fallbacks=[CommandHandler("admin", admin_open)],
        allow_reentry=True,
        name="gambling_admin_cms",
        persistent=True,
    )
