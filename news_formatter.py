"""GPT оформляет новость (заголовок+саммари ru/en), Python детерминированно
собирает Telegram HTML — жирный заголовок, цитаты, премиум-эмодзи по тегам.

Almost identical html-formatting policy to the rest of the bot (see constants.py
blockquote pattern, 16.07.2026): заголовок как есть, пояснение — в <blockquote>.
GPT возвращает ТОЛЬКО текстовые поля (без HTML) — это защищает от битой разметки
и инъекций: вся HTML-обвязка и html.escape делаются в Python, не в LLM-выводе.
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass

import httpx

# Премиум-эмодзи для новостей — ids из уже собранной базы (PREMIUM_EMOJI_BASE.md),
# те же паки, что и в остальном боте, для единого визуального стиля.
NEWS_EMOJI: dict[str, tuple[str, str]] = {
    "money": ("5301207025974271730", "\U0001f4b0"),      # 💰 Finance
    "growth": ("5301166722001168584", "\U0001f4c8"),     # 📈 Finance
    "trophy": ("5436011369197484799", "\U0001f3c6"),     # 🏆 InterfaceElements
    "rocket": ("5368842040647919004", "\U0001f680"),     # 🚀 Rich369
    "warning": ("5228837814879138578", "⚠️"),  # ⚠️ InterfaceElements
    "fire": ("5202175263495959587", "\U0001f525"),       # 🔥 football pack
    "news": ("5199527094035428887", "\U0001f4f0"),       # 📰 football pack
    "global": ("5361722793052382495", "\U0001f30e"),     # 🌎 Rich369
    "casino": ("5213044588771562736", "\U0001f3b0"),     # 🎰 casinoimg
}

_SYSTEM_PROMPT = """Ты — редактор новостного канала для Private Gambling \
Community, профессионального B2B-сообщества индустрии гемблинга/беттинга \
(владельцы компаний, C-level, менеджмент). Тебе дают заголовок и краткое \
содержание статьи с отраслевого издания (iGaming Business или SBC News).

Твоя задача — вернуть JSON (и только JSON, без markdown-обёртки) со следующими \
полями:
{
  "headline_ru": "заголовок на русском, деловой тон, без кликбейта, до 100 символов",
  "headline_en": "тот же заголовок на английском (можно близко к оригиналу), до 100 символов",
  "summary_ru": "2-4 предложения на русском: что произошло и почему это важно для профессионалов индустрии",
  "summary_en": "2-4 предложения на английском, та же суть",
  "tags": ["до 2 тегов из списка: money, growth, trophy, rocket, warning, fire, news, global, casino — выбери по смыслу новости"]
}

Пиши по-деловому, без эмодзи и HTML-тегов в тексте (просто plain text) — \
оформление добавит код. Не придумывай факты, которых нет в исходнике."""


@dataclass
class FormattedNews:
    headline_ru: str
    headline_en: str
    summary_ru: str
    summary_en: str
    tags: list[str]


async def format_with_gpt(api_key: str, model: str, title: str, summary: str,
                           source: str) -> FormattedNews | None:
    user_content = f"Источник: {source}\nЗаголовок: {title}\nСодержание: {summary}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "max_tokens": 600,
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
        return FormattedNews(
            headline_ru=_clamp(str(parsed["headline_ru"]).strip(), 150),
            headline_en=_clamp(str(parsed["headline_en"]).strip(), 150),
            summary_ru=_clamp(str(parsed["summary_ru"]).strip(), 500),
            summary_en=_clamp(str(parsed["summary_en"]).strip(), 500),
            tags=tags,
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


CAPTION_LIMIT = 1024


async def send_news_html(bot, chat_id: int, text: str, image_url: str | None,
                          parse_mode, reply_markup=None, **kwargs):
    """Фото+подпись, если влезает в лимит подписи (1024); иначе фото без подписи
    и полный текст (+кнопки) отдельным сообщением следом — чтобы не резать HTML
    на полуслове и не терять кнопки при обрезке."""
    if image_url and len(text) <= CAPTION_LIMIT:
        return await bot.send_photo(
            chat_id, image_url, caption=text, parse_mode=parse_mode,
            reply_markup=reply_markup, **kwargs,
        )
    if image_url:
        await bot.send_photo(chat_id, image_url, **kwargs)
        return await bot.send_message(
            chat_id, text, parse_mode=parse_mode, disable_web_page_preview=True,
            reply_markup=reply_markup, **kwargs,
        )
    return await bot.send_message(
        chat_id, text, parse_mode=parse_mode, disable_web_page_preview=True,
        reply_markup=reply_markup, **kwargs,
    )


def render_telegram_html(fn: FormattedNews, source: str, url: str) -> str:
    """Заголовок как есть (жирный) + цитаты для саммари — тот же стиль, что и
    во всём остальном боте (см. constants.py, blockquote-паттерн 16.07.2026)."""
    lead_emoji = ""
    if fn.tags:
        eid, fb = NEWS_EMOJI[fn.tags[0]]
        lead_emoji = f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji> '
    tail_emoji = ""
    if len(fn.tags) > 1:
        eid, fb = NEWS_EMOJI[fn.tags[1]]
        tail_emoji = f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji> '

    parts = [
        f"{lead_emoji}<b>{html.escape(fn.headline_ru)}</b>",
        f"<i>{html.escape(fn.headline_en)}</i>",
        "",
        f"<blockquote>{html.escape(fn.summary_ru)}</blockquote>",
        "",
        f"<blockquote>{html.escape(fn.summary_en)}</blockquote>",
        "",
        f'{tail_emoji}Источник: <a href="{html.escape(url)}">{html.escape(source)}</a>',
    ]
    return "\n".join(parts)
