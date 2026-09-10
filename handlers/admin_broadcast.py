"""Раздел /admin «Рассылка» — Live Broadcast Builder (манифест п.4): выбор
аудитории (все анкеты / по вертикали / по грейду), несколько текстовых
сообщений с опциональной URL-кнопкой, живой предпросмотр, фоновая отправка
с ретраем на флуд-контроль и отчётом админу.

WAIT_TEXT/WAIT_BTN_LABEL/WAIT_BTN_URL — собственные строковые константы
состояний (не пересекаются с int-состояниями admin_cms.py).
"""
from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter
from telegram.ext import ContextTypes

import constants as C
import logic
from country_formatter import flag_from_iso2
from handlers import admin_ui
from handlers.admin_ui import BROWSE
from handlers.group_captcha import spawn_background

logger = logging.getLogger(__name__)

WAIT_TEXT = "bc:text"
WAIT_BTN_LABEL = "bc:btnlabel"
WAIT_BTN_URL = "bc:btnurl"

MAX_ITEM_LEN = 4000
# сколько стран-кнопок показываем как есть, остальные — одной кнопкой «Остальные»
# (тот же приём, что и в island_summary_bot BROADCAST_COUNTRY_BUTTON_LIMIT)
COUNTRY_BUTTON_LIMIT = 20


def _bc(context) -> dict | None:
    return context.user_data.get("bc")


def _audience_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Все анкеты", callback_data="acms_bc_aud:all")],
        [InlineKeyboardButton("📊 По вертикали", callback_data="acms_bc_aud:vertical")],
        [InlineKeyboardButton("🎯 По грейду", callback_data="acms_bc_aud:grade")],
        [InlineKeyboardButton("🌍 По странам", callback_data="acms_bc_aud:country")],
        # Сегмент из отчёта владельца 06.09.2026: зарегистрировались, но
        # тариф не оплатили — их рейтинг не виден рекрутерам, и именно им
        # нужно объяснить, зачем платить.
        [InlineKeyboardButton("💤 Без подписки GURO ID", callback_data="acms_bc_aud:unpaid")],
        [InlineKeyboardButton("‹ Панель управления", callback_data="acms_home")],
    ])


def _vertical_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(v, callback_data=f"acms_bc_vert:{i}")]
        for i, v in enumerate(C.VERTICALS)
    ]
    rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_bc")])
    return InlineKeyboardMarkup(rows)


def _grade_options() -> tuple[str, ...]:
    return C.GRADES + (C.INVESTOR_GRADE,)


def _grade_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(g, callback_data=f"acms_bc_grade:{i}")]
        for i, g in enumerate(_grade_options())
    ]
    rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_bc")])
    return InlineKeyboardMarkup(rows)


def _country_kb(context) -> InlineKeyboardMarkup:
    storage = context.bot_data["storage"]
    segments = storage.country_broadcast_segments()  # уже отсортированы: n desc, потом имя
    visible = segments[:COUNTRY_BUTTON_LIMIT]
    overflow = segments[COUNTRY_BUTTON_LIMIT:]
    # индекс кнопки -> имя страны, для короткого callback_data (bc_pick_country)
    context.user_data["bc_countries"] = [row["country"] for row in visible]

    buttons = []
    for i, row in enumerate(visible):
        flag = flag_from_iso2(row["country_iso2"])
        label = f"{flag} {row['country']} — {row['n']}".strip()
        buttons.append(InlineKeyboardButton(label, callback_data=f"acms_bc_country:{i}"))

    columns = 2 if len(buttons) > 8 else 1
    rows = [buttons[i:i + columns] for i in range(0, len(buttons), columns)]

    if overflow:
        overflow_n = sum(row["n"] for row in overflow)
        rows.append([InlineKeyboardButton(
            f"🌐 Остальные страны — {overflow_n}", callback_data="acms_bc_country_other",
        )])

    rows.append([InlineKeyboardButton("‹ Назад", callback_data="acms_bc")])
    return InlineKeyboardMarkup(rows)


def _item_preview(item: dict) -> str:
    preview = " ".join(item["text"].split())
    if len(preview) > 60:
        preview = preview[:59] + "…"
    line = logic.html_escape(preview)
    if item.get("button_label"):
        line += f"  [🔗 «{logic.html_escape(item['button_label'])}»]"
    return line


def _builder_text(bc: dict) -> str:
    lines = [
        "📢 <b>Конструктор рассылки</b>\n",
        f"Аудитория: <b>{logic.html_escape(bc['audience']['label'])}</b>\n",
    ]
    if bc["items"]:
        lines.append("Сообщения:")
        for i, item in enumerate(bc["items"], 1):
            lines.append(f"{i}. {_item_preview(item)}")
    else:
        lines.append("Сообщений пока нет — добавьте хотя бы одно.")
    return "\n".join(lines)


def _builder_kb(bc: dict) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("➕ Добавить сообщение", callback_data="acms_bc_additem")]]
    if bc["items"]:
        rows.append([InlineKeyboardButton("🗑 Удалить последнее", callback_data="acms_bc_removelast")])
    rows.append([InlineKeyboardButton("👥 Кол-во получателей", callback_data="acms_bc_count")])
    if bc["items"]:
        rows.append([InlineKeyboardButton("🚀 Отправить", callback_data="acms_bc_send")])
    rows.append([InlineKeyboardButton("❌ Отменить конструктор", callback_data="acms_bc_cancel")])
    return InlineKeyboardMarkup(rows)


async def _show_builder(context) -> None:
    bc = _bc(context)
    await admin_ui.edit_screen(context, _builder_text(bc), _builder_kb(bc))


async def _show_dashboard(context):
    from handlers.admin_cms import _show_dashboard as show_dash
    await show_dash(context)


async def nav_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    if _bc(context) is None:
        await admin_ui.edit_screen(
            context, "📢 <b>Рассылка</b>\n\nВыберите аудиторию:", _audience_menu_kb(),
        )
    else:
        await _show_builder(context)
    return BROWSE


async def bc_audience_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["bc"] = {
        "audience": {"mode": "all", "value": None, "label": "Все анкеты"},
        "items": [],
    }
    await _show_builder(context)
    return BROWSE


async def bc_audience_unpaid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["bc"] = {
        "audience": {"mode": "unpaid", "value": None, "label": "Без подписки GURO ID"},
        "items": [],
    }
    await _show_builder(context)
    return BROWSE


async def bc_audience_vertical_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await admin_ui.edit_screen(context, "📊 Выберите вертикаль:", _vertical_kb())
    return BROWSE


async def bc_audience_grade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await admin_ui.edit_screen(context, "🎯 Выберите грейд:", _grade_kb())
    return BROWSE


async def bc_audience_country_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    storage = context.bot_data["storage"]
    if not storage.country_broadcast_segments():
        await q.answer("Пока никто не указал страну в анкете", show_alert=True)
        return BROWSE
    await q.answer()
    await admin_ui.edit_screen(context, "🌍 Выберите страну:", _country_kb(context))
    return BROWSE


async def bc_pick_vertical(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    idx = int(update.callback_query.data.split(":", 1)[1])
    vertical = C.VERTICALS[idx]
    context.user_data["bc"] = {
        "audience": {"mode": "vertical", "value": vertical, "label": f"Вертикаль: {vertical}"},
        "items": [],
    }
    await _show_builder(context)
    return BROWSE


async def bc_pick_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    idx = int(update.callback_query.data.split(":", 1)[1])
    grade = _grade_options()[idx]
    context.user_data["bc"] = {
        "audience": {"mode": "grade", "value": grade, "label": f"Грейд: {grade}"},
        "items": [],
    }
    await _show_builder(context)
    return BROWSE


async def bc_pick_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    idx = int(update.callback_query.data.split(":", 1)[1])
    countries = context.user_data.get("bc_countries", [])
    if idx >= len(countries):
        return BROWSE
    country = countries[idx]
    context.user_data["bc"] = {
        "audience": {"mode": "country", "value": country, "label": f"Страна: {country}"},
        "items": [],
    }
    await _show_builder(context)
    return BROWSE


async def bc_pick_country_other(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    storage = context.bot_data["storage"]
    overflow = [row["country"] for row in storage.country_broadcast_segments()[COUNTRY_BUTTON_LIMIT:]]
    context.user_data["bc"] = {
        "audience": {"mode": "country_other", "value": overflow, "label": "Остальные страны"},
        "items": [],
    }
    await _show_builder(context)
    return BROWSE


def _targets(context, bc: dict) -> list:
    storage = context.bot_data["storage"]
    mode = bc["audience"]["mode"]
    if mode == "vertical":
        return storage.profiles_for_broadcast(vertical=bc["audience"]["value"])
    if mode == "grade":
        return storage.profiles_for_broadcast(grade=bc["audience"]["value"])
    if mode == "country":
        return storage.profiles_for_broadcast(country=bc["audience"]["value"])
    if mode == "country_other":
        return storage.profiles_for_broadcast(country_in=bc["audience"]["value"])
    if mode == "unpaid":
        # Активность подписки — это функция от статуса и срока
        # (GL.subscription_active), а не колонка. Спрашиваем ровно тем же
        # вызовом, что и остальное приложение: своя SQL-копия правила
        # разъехалась бы с оригиналом, и письмо ушло бы оплатившим.
        guro = context.bot_data["guro_storage"]
        return [
            row for row in storage.profiles_for_broadcast()
            if not guro.is_subscribed(row["user_id"])
        ]
    return storage.profiles_for_broadcast()


async def bc_audience_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    bc = _bc(context)
    if bc is None:
        await q.answer("Конструктор сброшен, начните заново", show_alert=True)
        return BROWSE
    n = len(_targets(context, bc))
    await q.answer(f"Получателей: {n}", show_alert=True)
    return BROWSE


async def bc_add_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await admin_ui.edit_screen(
        context,
        "✍️ Пришлите текст сообщения (HTML-разметка поддерживается).",
        InlineKeyboardMarkup([[InlineKeyboardButton("‹ Отмена", callback_data="acms_bc")]]),
    )
    return WAIT_TEXT


async def bc_item_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    try:
        await update.message.delete()
    except Exception:  # noqa: BLE001
        pass
    if not text:
        return WAIT_TEXT
    context.user_data["bc_draft_item"] = {"text": text[:MAX_ITEM_LEN]}
    await admin_ui.edit_screen(
        context,
        "Добавить к этому сообщению кнопку-ссылку?",
        InlineKeyboardMarkup([[
            InlineKeyboardButton("Да", callback_data="acms_bc_btn:yes"),
            InlineKeyboardButton("Нет", callback_data="acms_bc_btn:no"),
        ]]),
    )
    return BROWSE


async def bc_btn_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    choice = q.data.split(":", 1)[1]
    draft = context.user_data.get("bc_draft_item")
    bc = _bc(context)
    if draft is None or bc is None:
        return BROWSE
    if choice == "no":
        bc["items"].append(draft)
        context.user_data.pop("bc_draft_item", None)
        await _show_builder(context)
        return BROWSE
    await admin_ui.edit_screen(context, "Текст на кнопке:")
    return WAIT_BTN_LABEL


async def bc_btn_label(update: Update, context: ContextTypes.DEFAULT_TYPE):
    label = (update.message.text or "").strip()
    try:
        await update.message.delete()
    except Exception:  # noqa: BLE001
        pass
    if not label:
        return WAIT_BTN_LABEL
    draft = context.user_data.get("bc_draft_item")
    if draft is None:
        return BROWSE
    draft["button_label"] = label[:60]
    await admin_ui.edit_screen(context, "Ссылка для кнопки (https://...):")
    return WAIT_BTN_URL


async def bc_btn_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()
    try:
        await update.message.delete()
    except Exception:  # noqa: BLE001
        pass
    if not url.startswith("http"):
        await admin_ui.edit_screen(context, "Похоже, это не ссылка. Пришлите URL вида https://...")
        return WAIT_BTN_URL
    draft = context.user_data.get("bc_draft_item")
    bc = _bc(context)
    if draft is None or bc is None:
        return BROWSE
    draft["button_url"] = url
    bc["items"].append(draft)
    context.user_data.pop("bc_draft_item", None)
    await _show_builder(context)
    return BROWSE


async def bc_remove_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    bc = _bc(context)
    if bc is None or not bc["items"]:
        await q.answer()
        return BROWSE
    bc["items"].pop()
    await q.answer("Удалено")
    await _show_builder(context)
    return BROWSE


async def bc_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("Конструктор отменён")
    context.user_data.pop("bc", None)
    context.user_data.pop("bc_draft_item", None)
    await _show_dashboard(context)
    return BROWSE


async def _send_to_user(context, user_id: int, items: list[dict]) -> str:
    """'success' | 'blocked' | 'error'."""
    for item in items:
        kwargs = {}
        if item.get("button_label") and item.get("button_url"):
            kwargs["reply_markup"] = InlineKeyboardMarkup(
                [[InlineKeyboardButton(item["button_label"], url=item["button_url"])]])
        sent = False
        for _attempt in range(3):
            try:
                await context.bot.send_message(
                    user_id, item["text"], parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True, **kwargs,
                )
                sent = True
                break
            except RetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 1)
            except Forbidden:
                return "blocked"
            except Exception:  # noqa: BLE001
                logger.exception("broadcast: send failed to %s", user_id)
                return "error"
        if not sent:
            return "error"
        await asyncio.sleep(0.05)
    return "success"


async def remove_from_community(context, user_id: int) -> bool:
    """Удаляет человека из группы сообщества. True, если удаление прошло.

    Кик, а не вечный бан: ban + unban убирает из группы, но не оставляет в
    чёрном списке — разблокирует бота и сможет вернуться. Причина ухода
    устранима, поэтому запирать дверь насовсем незачем.

    Никогда не поднимает исключение: вызывается из цикла рассылки по тысяче
    человек, и один отказ Telegram (нет прав, участника уже нет) не повод
    прерывать рассылку целиком.
    """
    settings = context.bot_data["settings"]
    chat_id = getattr(settings, "community_chat_id", 0)
    if not chat_id:
        return False
    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        await context.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("не удалось удалить %s из группы сообщества", user_id)
        return False


async def run_broadcast(context, admin_id: int, items: list[dict], targets: list,
                         audience_label: str) -> None:
    storage = context.bot_data["storage"]
    success = blocked = errors = removed = 0
    for row in targets:
        user_id = row["user_id"]
        outcome = await _send_to_user(context, user_id, items)
        if outcome == "success":
            success += 1
        elif outcome == "blocked":
            storage.mark_blocked(user_id)
            blocked += 1
            # Заблокировал бота — значит вышел из сообщества (просьба
            # владельца 08.09.2026). Блокировка выясняется только здесь, по
            # отказу Telegram при отправке, поэтому и удаляем здесь же.
            if await remove_from_community(context, user_id):
                removed += 1
        else:
            errors += 1
    storage.log_action(
        admin_id, "broadcast",
        f"{audience_label}: получателей {len(targets)}, успешно {success}, "
        f"заблокировали {blocked} (удалено из группы {removed}), ошибок {errors}",
    )
    try:
        await context.bot.send_message(
            admin_id,
            f"📢 Рассылка завершена ({logic.html_escape(audience_label)})\n\n"
            f"Получателей: {len(targets)}\nУспешно: {success}\n"
            f"Заблокировали бота: {blocked}\n"
            f"Удалено из группы: {removed}\n"
            f"Ошибок: {errors}",
        )
    except Exception:  # noqa: BLE001
        logger.exception("broadcast: не удалось отправить отчёт админу %s", admin_id)


async def bc_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    bc = _bc(context)
    if bc is None or not bc["items"]:
        await q.answer("Сначала добавьте хотя бы одно сообщение", show_alert=True)
        return BROWSE
    targets = _targets(context, bc)
    if not targets:
        await q.answer("Нет получателей под этот фильтр", show_alert=True)
        return BROWSE
    admin_id = update.effective_user.id
    items = list(bc["items"])
    label = bc["audience"]["label"]
    context.user_data.pop("bc", None)
    context.user_data.pop("bc_draft_item", None)
    # НЕ context.application.create_task — PTB ждёт такие задачи при
    # остановке (стоп/деплой завис бы до конца рассылки; на большую
    # аудиторию — минуты). Настоящий fire-and-forget.
    spawn_background(context, run_broadcast(context, admin_id, items, targets, label))
    await q.answer(f"Рассылка запущена, получателей: {len(targets)}. Отчёт придёт по готовности.",
                   show_alert=True)
    await _show_dashboard(context)
    return BROWSE
