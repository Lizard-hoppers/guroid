"""GPT оформляет анонимный тип-офф участника в короткую заметку-инсайд
(ru+en), Python детерминированно собирает Telegram HTML — та же политика
безопасности, что и в news_formatter.py: GPT возвращает ТОЛЬКО текстовые
поля (без HTML), вся разметка и html.escape собираются в Python.
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass

import httpx

from news_formatter import NEWS_EMOJI

_SYSTEM_PROMPT = """Ты — редактор рубрики инсайдов/слухов для Private \
Gambling Community, закрытого B2B-сообщества индустрии гемблинга/беттинга. \
Участник анонимно прислал сырой текст-инсайд. Перепиши его как короткую \
заметку в стиле лёгкой деловой светской хроники: живо, но без клеветы и \
оскорблений.

Правила:
- Если в тексте есть конкретные обвинения в адрес названных компаний/людей \
без доказательств — смягчи формулировку до "по неподтверждённым данным / по \
слухам на рынке", не подавай это как установленный факт.
- Не добавляй фактов, которых нет в исходном тексте, не выдумывай имена и \
компании.
- Если текст содержит оскорбления, разжигание ненависти, угрозы или похож на \
явную клевету/фейк — верни flagged=true (текст всё равно перепиши как есть,\
решение о публикации остаётся за модератором).

Верни JSON (и только JSON, без markdown-обёртки):
{
  "headline_ru": "короткий заголовок на русском, до 100 символов",
  "headline_en": "тот же заголовок на английском, до 100 символов",
  "summary_ru": "1-3 предложения на русском, разговорный деловой тон",
  "summary_en": "1-3 предложения на английском, та же суть",
  "tags": ["до 2 тегов из списка: money, growth, trophy, rocket, warning, fire, news, global, casino"],
  "flagged": true или false
}

Пиши plain text, без HTML-тегов и эмодзи в полях — оформление добавит код."""


@dataclass
class FormattedGossip:
    headline_ru: str
    headline_en: str
    summary_ru: str
    summary_en: str
    tags: list[str]
    flagged: bool


async def format_with_gpt(api_key: str, model: str, raw_text: str) -> FormattedGossip | None:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Сырой текст от участника:\n{raw_text}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.5,
        "max_tokens": 500,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers, json=payload, timeout=45,
        )
    if resp.status_code != 200:
        return None
    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        tags = [t for t in parsed.get("tags", []) if t in NEWS_EMOJI][:2]
        return FormattedGossip(
            headline_ru=_clamp(str(parsed["headline_ru"]).strip(), 150),
            headline_en=_clamp(str(parsed["headline_en"]).strip(), 150),
            summary_ru=_clamp(str(parsed["summary_ru"]).strip(), 500),
            summary_en=_clamp(str(parsed["summary_en"]).strip(), 500),
            tags=tags,
            flagged=bool(parsed.get("flagged", False)),
        )
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _clamp(text: str, limit: int) -> str:
    """Обрезает по границе слова, чтобы не резать HTML-теги при рендере."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip() + "…"


def render_telegram_html(fg: FormattedGossip) -> str:
    """🗣-заметка: заголовок жирным, саммари в цитатах — тот же визуальный
    стиль, что и у новостей (constants.py, blockquote-паттерн), но без
    источника/ссылки — источник анонимен по определению."""
    lead_emoji = ""
    if fg.tags:
        eid, fb = NEWS_EMOJI[fg.tags[0]]
        lead_emoji = f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji> '
    parts = [
        f"\U0001f5e3 {lead_emoji}<b>{html.escape(fg.headline_ru)}</b>",
        f"<i>{html.escape(fg.headline_en)}</i>",
        "",
        f"<blockquote>{html.escape(fg.summary_ru)}</blockquote>",
        "",
        f"<blockquote>{html.escape(fg.summary_en)}</blockquote>",
        "",
        "<i>Анонимно от участника сообщества / Anonymous community tip</i>",
    ]
    return "\n".join(parts)


def render_raw_fallback(raw_text: str) -> str:
    """Если GPT недоступен — публикуем исходный текст как есть (экранированный),
    чтобы сплетня не терялась; админ видит пометку и решает сам."""
    parts = [
        "\U0001f5e3 <b>Сплетня из сообщества</b>",
        "",
        f"<blockquote>{html.escape(raw_text)}</blockquote>",
        "",
        "<i>Анонимно от участника сообщества (не обработано ИИ)</i>",
    ]
    return "\n".join(parts)
