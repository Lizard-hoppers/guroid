"""RSS-источники отраслевых новостей (не AskGamblers — там Cloudflare + промо-контент).

iGaming Business и SBC News — легитимные B2B-издания про регулирование, сделки,
рынок. Разбор RSS 2.0 стандартной библиотекой (без feedparser), т.к. оба фида —
обычный WordPress RSS.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

import httpx

_MEDIA_NS = "{http://search.yahoo.com/mrss/}"

SOURCES: tuple[tuple[str, str], ...] = (
    ("iGaming Business", "https://igamingbusiness.com/feed/"),
    ("SBC News", "https://sbcnews.co.uk/feed/"),
)

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class NewsItem:
    source: str
    guid: str
    title: str
    url: str
    summary: str
    image_url: str | None


def _clean_html(raw: str) -> str:
    text = _TAG_RE.sub(" ", raw or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def fetch_source(client: httpx.AsyncClient, name: str, feed_url: str,
                        limit: int = 5) -> list[NewsItem]:
    resp = await client.get(feed_url, timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items: list[NewsItem] = []
    for item in root.findall("./channel/item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        if not guid or not title:
            continue
        description = item.findtext("description") or ""
        image_url = None
        media = item.find(f"{_MEDIA_NS}content")
        if media is not None:
            image_url = media.get("url")
        items.append(NewsItem(
            source=name, guid=guid, title=title, url=link,
            summary=_clean_html(description)[:1500], image_url=image_url,
        ))
    return items


async def fetch_all(limit_per_source: int = 5) -> list[NewsItem]:
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        result: list[NewsItem] = []
        for name, url in SOURCES:
            try:
                result.extend(await fetch_source(client, name, url, limit_per_source))
            except Exception:  # noqa: BLE001
                continue
        return result
