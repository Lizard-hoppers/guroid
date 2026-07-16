"""Клавиатуры бота (Блоки 1–7). Подписи берутся из content (CMS-override→дефолт)."""
from __future__ import annotations

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import constants as C
import logic
from content import Content

# Ведущий обычный эмодзи в начале подписи (срезается, если у кнопки есть premium-иконка).
_LEADING_EMOJI_RE = re.compile(
    r"^[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    r"←-⇿⌀-⏿⬀-⯿️‍⃣]+\s*"
)


def _strip_leading_emoji(text: str) -> str:
    """Срезает ведущий обычный эмодзи — чтобы при premium-иконке не было двух значков.
    Если после среза пусто (кнопка-эмодзи) — оставляем исходный текст."""
    stripped = _LEADING_EMOJI_RE.sub("", text).strip()
    return stripped if stripped else text


def link_button(label: str, url: str, style: str | None = None,
                emoji_id: str | None = None) -> InlineKeyboardButton:
    """URL-кнопка с опциональным цветом (style) и premium-эмодзи-иконкой (emoji_id).

    style/icon_custom_emoji_id не входят в модель PTB, поэтому прокидываются в Telegram
    через api_kwargs (как в Таки Вместе на aiogram — поля просто уходят в JSON).

    style=None (не задан в CMS) → синий (primary): все кнопки-ссылки по умолчанию
    синие (решение владельца 15.07.2026); «Обычный» в CMS даёт серый явно."""
    if style is None:
        style = "primary"
    extra: dict = {}
    if style and style != "default":
        extra["style"] = style
    if emoji_id:
        extra["icon_custom_emoji_id"] = str(emoji_id)
        label = _strip_leading_emoji(label)
    kwargs: dict = {"text": label, "url": url}
    if extra:
        kwargs["api_kwargs"] = extra
    return InlineKeyboardButton(**kwargs)


def group_menu_kb(storage, per_row: int = 2) -> InlineKeyboardMarkup | None:
    """Панель ссылок в группе из включённых menu_buttons (по per_row кнопок в ряд).

    Цвет, если не задан в CMS, — шахматный порядок синий/зелёный по позиции
    (решение владельца 15.07.2026: «много синего»), CMS-выбор приоритетнее."""
    enabled = [
        b for b in storage.menu_buttons(only_enabled=True) if (b["url"] or "").strip()
    ]
    buttons = []
    for i, b in enumerate(enabled):
        row, col = divmod(i, per_row)
        chess = "primary" if (row + col) % 2 == 0 else "success"
        buttons.append(
            link_button(b["label"] or b["url"], b["url"], b["style"] or chess, b["emoji_id"])
        )
    if not buttons:
        return None
    rows = [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]
    return InlineKeyboardMarkup(rows)


def lang_kb(content: Content) -> InlineKeyboardMarkup:
    # обе кнопки в одну строку; EN — зелёная, RU — синяя + премиум-иконка (глобус,
    # без флага РФ — требование владельца 16.07.2026)
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            content.btn("lang_en"), callback_data="lang:en",
            api_kwargs={"style": "success"},
        ),
        InlineKeyboardButton(
            content.btn("lang_ru"), callback_data="lang:ru",
            api_kwargs={"style": "primary", "icon_custom_emoji_id": C.LANG_RU_EMOJI_ID},
        ),
    ]])


def welcome_kb(content: Content) -> InlineKeyboardMarkup:
    # style/icon работают и на callback-кнопках (проверено 16.07.2026)
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        content.btn("start"), callback_data="start_form",
        api_kwargs={"style": "primary", "icon_custom_emoji_id": C.START_BUTTON_EMOJI_ID},
    )]])


def vertical_kb(content: Content) -> InlineKeyboardMarkup:
    rows, row = [], []
    for i in range(len(C.VERTICALS)):
        eid = C.VERTICAL_EMOJI_IDS[i] if i < len(C.VERTICAL_EMOJI_IDS) else None
        kw = {"text": content.btn(f"v_{i}"), "callback_data": f"v:{i}"}
        if eid:
            kw["api_kwargs"] = {"icon_custom_emoji_id": eid}
        row.append(InlineKeyboardButton(**kw))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def grade_kb(content: Content, vertical: str) -> InlineKeyboardMarkup:
    grades = C.grades_for(vertical)
    rows = []
    for i, g in enumerate(grades):
        key = "g_inv" if g == C.INVESTOR_GRADE else f"g_{i}"
        rows.append([InlineKeyboardButton(content.btn(key), callback_data=f"g:{i}")])
    rows.append([InlineKeyboardButton(content.btn("back"), callback_data="g_back")])
    return InlineKeyboardMarkup(rows)


def investor_type_kb(content: Content) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(content.btn(f"it_{i}"), callback_data=f"it:{i}")]
        for i in range(len(C.INVESTOR_TYPES))
    ]
    rows.append([InlineKeyboardButton(content.btn("back"), callback_data="g_back")])
    return InlineKeyboardMarkup(rows)


def investor_amount_kb(content: Content) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(content.btn(f"ia_{i}"), callback_data=f"ia:{i}")]
        for i in range(len(C.INVESTOR_AMOUNTS))
    ]
    rows.append([InlineKeyboardButton(content.btn("back"), callback_data="it_back")])
    return InlineKeyboardMarkup(rows)


def investor_needs_kb(content: Content, selected: list[int]) -> InlineKeyboardMarkup:
    rows = []
    for i in range(len(C.INVESTOR_NEEDS)):
        mark = "☑️ " if i in selected else "⬜ "
        rows.append(
            [InlineKeyboardButton(mark + content.btn(f"in_{i}"), callback_data=f"in:{i}")]
        )
    if selected:
        rows.append([InlineKeyboardButton(content.btn("done"), callback_data="in_done")])
    return InlineKeyboardMarkup(rows)


def profession_kb(content: Content, vertical: str, grade: str, page: int) -> InlineKeyboardMarkup:
    items = C.professions_for(vertical, grade)
    page = logic.clamp_page(page, len(items))
    rows = []
    for abs_idx, (_code, label) in logic.page_slice(items, page):
        rows.append([InlineKeyboardButton(label, callback_data=f"p:{abs_idx}")])

    total_pages = logic.page_count(len(items))
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(content.btn("prev"), callback_data=f"pg:{page - 1}"))
        nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(content.btn("next"), callback_data=f"pg:{page + 1}"))
        rows.append(nav)

    rows.append([InlineKeyboardButton(content.btn("other"), callback_data="p_other")])
    rows.append([InlineKeyboardButton(content.btn("back"), callback_data="p_back")])
    return InlineKeyboardMarkup(rows)


def vertical_other_kb(content: Content) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(content.btn("back"), callback_data="vo_back")]]
    )


def profession_other_kb(content: Content) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(content.btn("back"), callback_data="po_back")]]
    )


def linkedin_kb(content: Content) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(content.btn("skip"), callback_data="skip_li")]]
    )


def final_kb(content: Content, invite_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[link_button(
        content.btn("join"), invite_url, emoji_id=C.JOIN_BUTTON_EMOJI_ID
    )]])
