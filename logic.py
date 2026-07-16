"""Чистые функции логики анкеты: пагинация, форматирование карточки и строки таблицы."""
from __future__ import annotations

import math
import random

import constants as C

PROFILE_FIELDS = (
    "vertical",
    "grade",
    "profession",
    "investor_type",
    "investor_amount",
    "investor_needs",
    "request",
    "name",
    "company",
    "linkedin",
)


def html_escape(text: str | None) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def page_count(total: int, per_page: int = C.PROFESSIONS_PER_PAGE) -> int:
    if total <= 0:
        return 1
    return math.ceil(total / per_page)


def clamp_page(page: int, total: int, per_page: int = C.PROFESSIONS_PER_PAGE) -> int:
    last = page_count(total, per_page) - 1
    return max(0, min(page, last))


def page_slice(
    items: list, page: int, per_page: int = C.PROFESSIONS_PER_PAGE
) -> list[tuple[int, object]]:
    """Возвращает [(абсолютный_индекс, элемент), ...] для страницы."""
    start = page * per_page
    end = start + per_page
    return list(enumerate(items))[start:end]


def needs_to_text(indexes: list[int]) -> str:
    labels = [C.INVESTOR_NEEDS[i] for i in indexes if 0 <= i < len(C.INVESTOR_NEEDS)]
    return "; ".join(labels)


def profile_to_sheet_row(profile: dict, created_at: str) -> list[str]:
    """Строка для Google Sheets в порядке заголовков таблицы."""
    return [
        created_at,
        str(profile.get("user_id", "")),
        profile.get("username", "") or "",
        profile.get("vertical", "") or "",
        profile.get("grade", "") or "",
        profile.get("profession", "") or "",
        profile.get("investor_type", "") or "",
        profile.get("investor_amount", "") or "",
        profile.get("investor_needs", "") or "",
        profile.get("request", "") or "",
        profile.get("name", "") or "",
        profile.get("company", "") or "",
        profile.get("linkedin", "") or "",
    ]


def profile_to_admin_card(profile: dict) -> str:
    """HTML-карточка новой анкеты для админ-чата."""
    e = html_escape
    username = profile.get("username")
    uname = f"@{e(username)}" if username else "—"
    lines = [
        "🆕 <b>Новая анкета</b>",
        f"👤 {e(profile.get('name'))} ({uname}, id <code>{profile.get('user_id')}</code>)",
        f"🏷 Вертикаль: <b>{e(profile.get('vertical'))}</b>",
        f"🎚 Грейд: {e(profile.get('grade'))}",
    ]
    if profile.get("profession"):
        lines.append(f"💼 Должность: {e(profile.get('profession'))}")
    if profile.get("investor_type"):
        lines.append(f"💰 Тип инвестора: {e(profile.get('investor_type'))}")
    if profile.get("investor_amount"):
        lines.append(f"💵 Суммы: {e(profile.get('investor_amount'))}")
    if profile.get("investor_needs"):
        lines.append(f"🎯 Ищет: {e(profile.get('investor_needs'))}")
    lines.append(f"📝 Запрос: {e(profile.get('request'))}")
    lines.append(f"🏢 Компания: {e(profile.get('company'))}")
    if profile.get("linkedin") and profile.get("linkedin") != C.SKIPPED_VALUE:
        lines.append(f"🔗 Контакт: {e(profile.get('linkedin'))}")
    return "\n".join(lines)


# =========================================================================
# Капча для новичков в группе (второй уровень бота) — чистая логика.
# =========================================================================

CAPTCHA_PLACEHOLDER = "{captcha}"


def make_captcha(rng: random.Random | None = None) -> tuple[int, int]:
    """Случайный пример сложения A+B (двузначные слагаемые, ответ всегда > 0)."""
    r = rng or random
    a = r.randint(10, 99)
    b = r.randint(2, 49)
    return a, b


def captcha_options(answer: int, count: int = 4, rng: random.Random | None = None) -> list[int]:
    """Список из `count` вариантов: верный ответ + близкие отвлекающие, перемешано.

    Гарантии: верный ответ присутствует ровно один раз, все варианты различны,
    положительны, длина == count.
    """
    r = rng or random
    count = max(2, count)
    opts = {answer}
    guard = 0
    while len(opts) < count and guard < 500:
        guard += 1
        cand = answer + r.randint(-12, 12)
        if cand > 0 and cand != answer:
            opts.add(cand)
    # добор на краю диапазона (на случай маленького ответа)
    n = answer + 1
    while len(opts) < count:
        if n > 0 and n != answer:
            opts.add(n)
        n += 1
    out = list(opts)
    r.shuffle(out)
    return out


def render_captcha_text(template: str, a: int, b: int) -> str:
    """Подставляет пример в шаблон приветствия. Без плейсхолдера — дописывает в конец."""
    task = f"<b>{a} + {b} = ?</b>"
    if CAPTCHA_PLACEHOLDER in template:
        return template.replace(CAPTCHA_PLACEHOLDER, task)
    return f"{template}\n\n{task}"
