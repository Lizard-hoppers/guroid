"""Основной флоу анкеты (Блоки 1–7) на ConversationHandler.

Clean Chat: у пользователя всегда один активный экран — он редактируется на
каждом шаге, временные сообщения пользователя удаляются.
Все тексты и подписи кнопок берутся из content (CMS-override → дефолт).
"""
from __future__ import annotations

import logging
import time
from enum import IntEnum, auto
from pathlib import Path

from telegram import (
    InlineKeyboardMarkup,
    InputMediaAnimation,
    InputMediaPhoto,
    InputMediaVideo,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
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
from country_formatter import normalize_country
from handlers import admin_ui
from handlers.admin_profiles import send_card_message as _open_profile_card
from handlers.admin_users import send_card_message as _open_user_card
from handlers.group_captcha import delete_gate_prompts, post_singleton_group_message, unmute_after_profile

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


class S(IntEnum):
    WELCOME = auto()
    VERTICAL = auto()
    VERTICAL_OTHER = auto()
    GRADE = auto()
    INV_TYPE = auto()
    INV_AMOUNT = auto()
    INV_NEEDS = auto()
    PROFESSION = auto()
    PROFESSION_OTHER = auto()
    REQUEST = auto()
    NAME = auto()
    COMPANY = auto()
    LINKEDIN = auto()
    # выбор языка; в КОНЦЕ enum, чтобы не сдвинуть значения persisted-состояний
    LANG = auto()
    # страна; тоже в КОНЦЕ enum по той же причине (не сдвигать persisted-состояния)
    COUNTRY = auto()


# --- helpers --------------------------------------------------------------

def _profile(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault("profile", {})


def _content(context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "ru")
    return context.bot_data["content"].view(lang)


_INPUT_MEDIA = {
    "animation": InputMediaAnimation,
    "photo": InputMediaPhoto,
    "video": InputMediaVideo,
}


async def _delete_screen(context, chat, mid) -> None:
    try:
        await context.bot.delete_message(chat, mid)
    except Exception:  # noqa: BLE001
        pass


async def _send_media(context, chat, file_id, mtype, caption, kb):
    if mtype == "animation":
        return await context.bot.send_animation(
            chat, file_id, caption=caption, reply_markup=kb, parse_mode=ParseMode.HTML
        )
    if mtype == "video":
        return await context.bot.send_video(
            chat, file_id, caption=caption, reply_markup=kb, parse_mode=ParseMode.HTML
        )
    return await context.bot.send_photo(
        chat, file_id, caption=caption, reply_markup=kb, parse_mode=ParseMode.HTML
    )


async def _show(context, key: str, kb=None, text_vars: dict[str, str] | None = None) -> None:
    """Единственный экран Clean Chat. С медиа — фото/гиф/видео + подпись, иначе текст.

    Переход text↔media пересоздаёт сообщение (Telegram не редактирует тип); внутри
    одного типа — редактирование на месте (без мигания). text_vars — подстановка
    плейсхолдеров вида {ключ} в CMS-тексте (например {members} — живой счётчик).
    """
    c = _content(context)
    text = c.txt(key)
    if text_vars:
        for placeholder, value in text_vars.items():
            text = text.replace(placeholder, value)
    media = c.media(key)
    chat = context.user_data.get("screen_chat")
    mid = context.user_data.get("screen_id")
    kind = context.user_data.get("screen_kind")
    if chat is None:
        return

    if media:
        file_id, mtype = media
        if mid and kind == "media":
            try:
                await context.bot.edit_message_media(
                    media=_INPUT_MEDIA.get(mtype, InputMediaPhoto)(
                        media=file_id, caption=text, parse_mode=ParseMode.HTML
                    ),
                    chat_id=chat,
                    message_id=mid,
                    reply_markup=kb,
                )
                return
            except BadRequest as exc:
                if "not modified" in str(exc).lower():
                    try:
                        await context.bot.edit_message_reply_markup(
                            chat_id=chat, message_id=mid, reply_markup=kb
                        )
                    except BadRequest:
                        pass
                    return
            except Exception:  # noqa: BLE001
                logger.debug("edit media failed", exc_info=True)
        if mid:
            await _delete_screen(context, chat, mid)
        msg = await _send_media(context, chat, file_id, mtype, text, kb)
        context.user_data["screen_id"] = msg.message_id
        context.user_data["screen_kind"] = "media"
        return

    # текстовый экран
    if mid and kind == "text":
        try:
            await context.bot.edit_message_text(
                text,
                chat_id=chat,
                message_id=mid,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
        except Exception:  # noqa: BLE001
            logger.debug("edit text failed", exc_info=True)
    if mid:
        await _delete_screen(context, chat, mid)
    msg = await context.bot.send_message(
        chat,
        text,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    context.user_data["screen_id"] = msg.message_id
    context.user_data["screen_kind"] = "text"


async def _delete_user_msg(update: Update) -> None:
    try:
        await update.message.delete()
    except Exception:  # noqa: BLE001
        pass


# --- Блок 1: приветствие --------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _delete_user_msg(update)  # Clean Chat: убираем /start
    user = update.effective_user
    settings = context.bot_data["settings"]

    # /start прямо в группе (не по deep-link — те всегда открывают личку) не
    # должен разворачивать анкету/админ-панель на виду у всех. Один активный
    # слот на чат (post_singleton_group_message) — повторные попытки не копятся.
    if update.effective_chat.type != "private":
        chat_id = update.effective_chat.id
        await post_singleton_group_message(
            context, chat_id, "start_redirect",
            lambda: context.bot.send_message(
                chat_id,
                "Анкету нужно проходить в личном сообщении с ботом — нажмите кнопку ниже 👇",
                reply_markup=InlineKeyboardMarkup([[ui.link_button(
                    "➡️ Перейти к боту", f"https://t.me/{context.bot.username}", style="primary",
                )]]),
            ),
        )
        return ConversationHandler.END

    # Всё для админов проверяем ДО user_data.clear() ниже — иначе
    # delete_previous_screen не найдёт adm_chat/adm_mid (текущий экран
    # /admin), и старое меню-список останется висеть в чате рядом с новым.
    if settings.is_admin(user.id):
        await delete_gate_prompts(context, user.id)

        # deep-link из списка «Анкеты»/«Пользователи» (клик по ID) -> сразу карточка
        args = getattr(context, "args", None) or []
        payload = args[0] if args else ""
        target = payload.split("_", 1)[1] if "_" in payload else ""
        if target.isdigit() and (payload.startswith("u_") or payload.startswith("p_")):
            if payload.startswith("u_"):
                await _open_user_card(context, update.effective_chat.id, int(target))
            else:
                await _open_profile_card(context, update.effective_chat.id, int(target))
            return ConversationHandler.END

        # обычный /start админа — сразу открываем панель управления, без
        # промежуточного «наберите /admin». ВАЖНО: admin_cms.admin_open() тут
        # вызывается напрямую, в обход диспетчера gambling_admin_cms — если
        # это первое ЛИЧНОЕ обращение админа к боту вообще (ни разу не жал
        # /admin), у gambling_admin_cms ещё нет активной сессии для этого
        # чата, и кнопки на дашборде не сработают, пока админ не откроет
        # /admin один раз (та же оговорка, что и у карточек по
        # forward/deep-link — см. admin_users.py). Для уже когда-либо
        # открывавших /admin (обычный случай) работает сразу.
        from handlers.admin_cms import admin_open
        await admin_ui.delete_previous_screen(context)
        await admin_open(update, context)
        return ConversationHandler.END

    context.user_data.clear()
    context.user_data["screen_chat"] = update.effective_chat.id

    _consume_referral_payload(context, user)

    # гейт группы: юзер пришёл в бота — подчищаем просьбу «пройди анкету» в группе
    await delete_gate_prompts(context, user.id)
    await _show(context, "lang_select", ui.lang_kb(_content(context)))
    return S.LANG


def _consume_referral_payload(context: ContextTypes.DEFAULT_TYPE, user) -> None:
    """Реф-ссылка `?start=ref_<referrer_id>_<slot>` — привязывает слот к
    ЭТОМУ юзеру, только если он новый (без анкеты) и ещё не привязан к
    другому рефереру (первая ссылка выигрывает, повторные /start её не
    перезапишут)."""
    args = getattr(context, "args", None) or []
    payload = args[0] if args else ""
    if not payload.startswith("ref_"):
        return
    parts = payload[len("ref_"):].split("_")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return
    referrer_id, slot = int(parts[0]), int(parts[1])
    if referrer_id == user.id:
        return
    storage = context.bot_data["storage"]
    if storage.has_profile(user.id) or storage.get_referrer_of(user.id):
        return
    storage.consume_referral_link(referrer_id, slot, user.id, user.username)


_MEMBER_COUNT_TTL = 300  # сек — не дёргать API на каждый /start
_MEMBER_COUNT_FALLBACK = 4000


async def _member_count(context) -> int:
    """Живое кол-во участников группы сообщества, с кэшем на 5 минут.

    Без COMMUNITY_CHAT_ID или при ошибке API — последнее известное значение,
    изначально статичная оценка (как было в тексте раньше)."""
    settings = context.bot_data["settings"]
    cache = context.bot_data.setdefault(
        "member_count_cache", {"value": _MEMBER_COUNT_FALLBACK, "ts": 0.0}
    )
    now = time.monotonic()
    if now - cache["ts"] < _MEMBER_COUNT_TTL or not settings.community_chat_id:
        return cache["value"]
    try:
        cache["value"] = await context.bot.get_chat_member_count(settings.community_chat_id)
        cache["ts"] = now
    except Exception:  # noqa: BLE001
        logger.debug("member count fetch failed", exc_info=True)
    return cache["value"]


async def choose_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    context.user_data["lang"] = "en" if q.data == "lang:en" else "ru"
    count = await _member_count(context)
    await _show(
        context, "welcome", ui.welcome_kb(_content(context)),
        text_vars={"{members}": str(count)},
    )
    return S.WELCOME


async def begin_form(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await _show(context, "ask_vertical", ui.vertical_kb(_content(context)))
    return S.VERTICAL


# --- Блок 2: вертикаль ----------------------------------------------------

async def pick_vertical(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    c = _content(context)
    idx = int(q.data.split(":", 1)[1])
    name = C.VERTICALS[idx]
    context.user_data["vertical_key"] = name
    if name == "Other":
        await _show(context, "ask_vertical_other", ui.vertical_other_kb(c))
        return S.VERTICAL_OTHER
    _profile(context)["vertical"] = name
    await _show(context, "ask_grade", ui.grade_kb(c, name))
    return S.GRADE


async def vertical_other_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    await _delete_user_msg(update)
    c = _content(context)
    if not text:
        await _show(context, "ask_vertical_other", ui.vertical_other_kb(c))
        return S.VERTICAL_OTHER
    _profile(context)["vertical"] = f"Other: {text}"
    await _show(context, "ask_grade", ui.grade_kb(c, "Other"))
    return S.GRADE


async def vertical_other_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    c = _content(context)
    context.user_data.pop("vertical_key", None)
    await _show(context, "ask_vertical", ui.vertical_kb(c))
    return S.VERTICAL


# --- Грейд ----------------------------------------------------------------

async def pick_grade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    c = _content(context)
    vkey = context.user_data["vertical_key"]
    idx = int(q.data.split(":", 1)[1])
    grade = C.grades_for(vkey)[idx]
    _profile(context)["grade"] = grade

    if grade == C.INVESTOR_GRADE:
        await _show(context, "ask_investor_type", ui.investor_type_kb(c))
        return S.INV_TYPE

    context.user_data["page"] = 0
    await _show(context, "ask_profession", ui.profession_kb(c, vkey, grade, 0))
    return S.PROFESSION


async def grade_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    c = _content(context)
    await _show(context, "ask_vertical", ui.vertical_kb(c))
    return S.VERTICAL


# --- Инвестор-ветка (только Gambling) ------------------------------------

async def pick_investor_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    c = _content(context)
    idx = int(q.data.split(":", 1)[1])
    _profile(context)["investor_type"] = c.btn(f"it_{idx}")
    await _show(context, "ask_investor_amount", ui.investor_amount_kb(c))
    return S.INV_AMOUNT


async def investor_type_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    c = _content(context)
    vkey = context.user_data["vertical_key"]
    await _show(context, "ask_grade", ui.grade_kb(c, vkey))
    return S.GRADE


async def pick_investor_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    c = _content(context)
    idx = int(q.data.split(":", 1)[1])
    _profile(context)["investor_amount"] = c.btn(f"ia_{idx}")
    context.user_data["needs"] = []
    await _show(context, "ask_investor_needs", ui.investor_needs_kb(c, []))
    return S.INV_NEEDS


async def investor_amount_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    c = _content(context)
    await _show(context, "ask_investor_type", ui.investor_type_kb(c))
    return S.INV_TYPE


async def toggle_need(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    c = _content(context)
    idx = int(q.data.split(":", 1)[1])
    selected = context.user_data.setdefault("needs", [])
    if idx in selected:
        selected.remove(idx)
    else:
        selected.append(idx)
    await _show(context, "ask_investor_needs", ui.investor_needs_kb(c, selected))
    return S.INV_NEEDS


async def investor_needs_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    c = _content(context)
    selected = sorted(context.user_data.get("needs", []))
    _profile(context)["investor_needs"] = "; ".join(c.btn(f"in_{i}") for i in selected)
    return await _go_request(context)


# --- Профессия ------------------------------------------------------------

async def profession_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    c = _content(context)
    page = int(q.data.split(":", 1)[1])
    context.user_data["page"] = page
    p = _profile(context)
    await _show(
        context,
        "ask_profession",
        ui.profession_kb(c, context.user_data["vertical_key"], p["grade"], page),
    )
    return S.PROFESSION


async def pick_profession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    idx = int(q.data.split(":", 1)[1])
    vkey = context.user_data["vertical_key"]
    p = _profile(context)
    items = C.professions_for(vkey, p["grade"])
    _code, label = items[idx]
    p["profession"] = label
    return await _go_request(context)


async def profession_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await _show(context, "ask_profession_other", ui.profession_other_kb(_content(context)))
    return S.PROFESSION_OTHER


async def profession_other_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    await _delete_user_msg(update)
    if not text:
        await _show(context, "ask_profession_other", ui.profession_other_kb(_content(context)))
        return S.PROFESSION_OTHER
    _profile(context)["profession"] = text
    return await _go_request(context)


async def profession_other_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    c = _content(context)
    vkey = context.user_data["vertical_key"]
    grade = _profile(context)["grade"]
    page = context.user_data.get("page", 0)
    await _show(context, "ask_profession", ui.profession_kb(c, vkey, grade, page))
    return S.PROFESSION


async def profession_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    c = _content(context)
    vkey = context.user_data["vertical_key"]
    await _show(context, "ask_grade", ui.grade_kb(c, vkey))
    return S.GRADE


async def noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return S.PROFESSION


# --- Блоки 3–6: свободный текст ------------------------------------------

async def _go_request(context) -> int:
    await _show(context, "ask_request")
    return S.REQUEST


async def request_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    await _delete_user_msg(update)
    if not text:
        await _show(context, "ask_request")
        return S.REQUEST
    _profile(context)["request"] = text
    await _show(context, "ask_name")
    return S.NAME


async def name_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    await _delete_user_msg(update)
    if not text:
        await _show(context, "ask_name")
        return S.NAME
    _profile(context)["name"] = text
    await _show(context, "ask_country")
    return S.COUNTRY


async def country_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    await _delete_user_msg(update)
    if not text:
        await _show(context, "ask_country")
        return S.COUNTRY
    settings = context.bot_data["settings"]
    country, iso2 = text, ""
    if settings.openai_api_key:
        normalized = await normalize_country(settings.openai_api_key, settings.openai_model, text)
        if normalized is not None:
            country, iso2 = normalized.country_ru, normalized.iso2
    p = _profile(context)
    p["country"] = country
    p["country_iso2"] = iso2
    await _show(context, "ask_company")
    return S.COMPANY


async def company_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    await _delete_user_msg(update)
    c = _content(context)
    if not text:
        await _show(context, "ask_company")
        return S.COMPANY
    _profile(context)["company"] = text
    await _show(context, "ask_linkedin", ui.linkedin_kb(c))
    return S.LINKEDIN


async def linkedin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    await _delete_user_msg(update)
    c = _content(context)
    if not text:
        await _show(context, "ask_linkedin", ui.linkedin_kb(c))
        return S.LINKEDIN
    _profile(context)["linkedin"] = text
    return await _finish(update, context)


async def linkedin_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    _profile(context)["linkedin"] = C.SKIPPED_VALUE
    return await _finish(update, context)


# --- Блок 7: завершение ---------------------------------------------------

async def _finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    c = _content(context)
    profile = _profile(context)
    profile["user_id"] = user.id
    profile["username"] = user.username or ""
    profile["lang"] = context.user_data.get("lang", "ru")

    settings = context.bot_data["settings"]
    storage = context.bot_data["storage"]
    sheet = context.bot_data["sheet"]

    profile_id, created_at = storage.save_profile(profile)

    # Google Sheets — best-effort
    try:
        if sheet.append_row(logic.profile_to_sheet_row(profile, created_at)):
            storage.mark_synced(profile_id)
    except Exception:  # noqa: BLE001
        logger.exception("sheet append failed for profile %s", profile_id)

    # Забанен администратором (storage.banned_users, отдельно от group_mutes) —
    # анкета НЕ должна снимать бан и НЕ должна выдавать доступ в группу.
    banned = storage.is_banned(user.id)

    # гейт группы: анкета пройдена — размучиваем и шлём приветствие в группах
    # (кроме забаненных — их ограничение должно остаться в силе)
    if not banned:
        try:
            await unmute_after_profile(context, user)
        except Exception:  # noqa: BLE001
            logger.exception("gate: unmute after profile failed for %s", user.id)

    # уведомление админам
    card = logic.profile_to_admin_card(profile, banned=banned)
    for admin_id in settings.admin_ids:
        try:
            await context.bot.send_message(
                admin_id, card, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            )
        except Exception:  # noqa: BLE001
            logger.debug("notify admin %s failed", admin_id, exc_info=True)

    if banned:
        await _show(context, "banned_notice")
    else:
        await _send_media_kit(context, user, c)
        invite_url = await _make_invite_link(context, user)
        await _show(context, "final", ui.final_kb(c, invite_url, settings.guro_id_webapp_url))
    context.user_data.clear()
    return ConversationHandler.END


async def _send_media_kit(context, user, c) -> None:
    """Медиакит GURO (PDF) — отдельным документом, до финального экрана с инвайтом.

    Показывает ценность сообщества (аудитория, «Гэмблинговый суд», спонсорские тарифы)
    в момент максимальной вовлечённости, сразу после анкеты. Best-effort: сбой отправки
    не должен блокировать выдачу инвайта.
    """
    lang = context.user_data.get("lang", "ru")
    rel_path = C.MEDIA_KIT_EN_PATH if lang == "en" else C.MEDIA_KIT_RU_PATH
    path = BASE_DIR / rel_path
    if not path.is_file():
        logger.warning("media kit file missing: %s", path)
        return
    chat_id = context.user_data.get("screen_chat") or user.id
    try:
        with path.open("rb") as f:
            await context.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=path.name,
                caption=c.txt("media_kit_caption"),
                parse_mode=ParseMode.HTML,
            )
    except Exception:  # noqa: BLE001
        logger.exception("media kit send failed for %s", user.id)


async def _make_invite_link(context, user) -> str:
    """Одноразовая инвайт-ссылка в группу сообщества (member_limit=1 — сгорает после
    первого использования). Без community_chat_id или при ошибке API — статичная
    ссылка-заглушка community_invite_url (как раньше)."""
    settings = context.bot_data["settings"]
    if not settings.community_chat_id:
        return settings.community_invite_url
    try:
        link = await context.bot.create_chat_invite_link(
            settings.community_chat_id, member_limit=1, name=f"pgc_{user.id}"[:32],
        )
        return link.invite_link
    except Exception:  # noqa: BLE001
        logger.exception("invite: не удалось создать одноразовую ссылку для %s", user.id)
        return settings.community_invite_url


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if update.message:
        await update.message.reply_text("Анкета отменена. Наберите /start, чтобы начать заново.")
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            S.LANG: [CallbackQueryHandler(choose_lang, pattern=r"^lang:(ru|en)$")],
            S.WELCOME: [CallbackQueryHandler(begin_form, pattern=r"^start_form$")],
            S.VERTICAL: [CallbackQueryHandler(pick_vertical, pattern=r"^v:\d+$")],
            S.VERTICAL_OTHER: [
                CallbackQueryHandler(vertical_other_back, pattern=r"^vo_back$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, vertical_other_text),
            ],
            S.GRADE: [
                CallbackQueryHandler(grade_back, pattern=r"^g_back$"),
                CallbackQueryHandler(pick_grade, pattern=r"^g:\d+$"),
            ],
            S.INV_TYPE: [
                CallbackQueryHandler(investor_type_back, pattern=r"^g_back$"),
                CallbackQueryHandler(pick_investor_type, pattern=r"^it:\d+$"),
            ],
            S.INV_AMOUNT: [
                CallbackQueryHandler(investor_amount_back, pattern=r"^it_back$"),
                CallbackQueryHandler(pick_investor_amount, pattern=r"^ia:\d+$"),
            ],
            S.INV_NEEDS: [
                CallbackQueryHandler(investor_needs_done, pattern=r"^in_done$"),
                CallbackQueryHandler(toggle_need, pattern=r"^in:\d+$"),
            ],
            S.PROFESSION: [
                CallbackQueryHandler(profession_back, pattern=r"^p_back$"),
                CallbackQueryHandler(profession_other, pattern=r"^p_other$"),
                CallbackQueryHandler(profession_page, pattern=r"^pg:\d+$"),
                CallbackQueryHandler(noop, pattern=r"^noop$"),
                CallbackQueryHandler(pick_profession, pattern=r"^p:\d+$"),
            ],
            S.PROFESSION_OTHER: [
                CallbackQueryHandler(profession_other_back, pattern=r"^po_back$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, profession_other_text),
            ],
            S.REQUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, request_text)],
            S.NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_text)],
            S.COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country_text)],
            S.COMPANY: [MessageHandler(filters.TEXT & ~filters.COMMAND, company_text)],
            S.LINKEDIN: [
                CallbackQueryHandler(linkedin_skip, pattern=r"^skip_li$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, linkedin_text),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
        name="gambling_form",
        persistent=True,
    )
