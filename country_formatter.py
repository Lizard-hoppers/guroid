"""Нормализация страны, введённой участником в анкете свободным текстом
(опечатки/сокращения/на английском/разговорно) — через GPT. Та же политика
безопасности, что и в news_formatter.py/gossip_formatter.py: GPT возвращает
ТОЛЬКО простые текстовые поля (без HTML), вся дальнейшая обработка (в т.ч.
флаг из ISO-кода) детерминирована в Python.

Флаг эмодзи — не статичный словарь (как в island_summary_bot), а
вычисляется из ISO 3166-1 alpha-2 кода юникод-трюком (regional indicator
symbols): работает для ЛЮБОЙ страны, ничего вручную поддерживать не нужно.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

_SYSTEM_PROMPT = """Ты нормализуешь название страны, которое участник указал \
в анкете B2B-сообщества индустрии гемблинга/беттинга. Текст мог быть с \
опечатками, сокращением, на английском или разговорным (например "азер", \
"USA", "росия", "объединенные арабские эмираты").

Верни JSON (и только JSON, без markdown-обёртки):
{
  "country_ru": "официальное короткое русское название страны (например \
Азербайджан, США, ОАЭ, Великобритания) или null, если текст не похож ни на \
одну страну (мусор, пустое, неразборчиво, название города без страны)",
  "iso2": "двухбуквенный код страны ISO 3166-1 alpha-2 заглавными латинскими \
буквами (например AZ, US, AE, GB) или null, если country_ru тоже null"
}"""


@dataclass
class NormalizedCountry:
    country_ru: str
    iso2: str


def flag_from_iso2(iso2: str | None) -> str:
    """🇦🇿-стиль флаг из двухбуквенного ISO-кода, без словарей."""
    if not iso2 or len(iso2) != 2 or not iso2.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2.upper())


async def normalize_country(api_key: str, model: str, raw_text: str) -> NormalizedCountry | None:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Страна из анкеты: {raw_text}"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 100,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers, json=payload, timeout=20,
        )
    if resp.status_code != 200:
        return None
    try:
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        country_ru = parsed.get("country_ru")
        iso2 = parsed.get("iso2")
        if not country_ru or not iso2 or len(str(iso2)) != 2 or not str(iso2).isalpha():
            return None
        return NormalizedCountry(country_ru=str(country_ru).strip()[:80], iso2=str(iso2).strip().upper())
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None
