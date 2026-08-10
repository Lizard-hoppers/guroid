"""Витрина разработчика GURO ID (@lizard_hoppers) — персональная карточка,
подставляется вместо обычного профиля/результата поиска ТОЛЬКО для этого
одного аккаунта. Данные статичные (не из profiles/guro_users — у автора
может не быть анкеты в этом боте), см. guro_id_api.py handle_me/handle_search.
"""
from __future__ import annotations

USERNAME = "lizard_hoppers"

PAYLOAD = {
    "username": USERNAME,
    "name": "Pavel — разработчик Telegram-ботов и Mini Apps",
    "is_showcase": True,
    "locked": False,
    "showcase": {
        "tagline": "От идеи до продакшна: боты и Mini Apps под ключ",
        "bio": (
            "Строю Telegram-ботов и Mini Apps для комьюнити и бизнеса — от "
            "антифрод-верификации и live-геймификации до полноценных "
            "мини-приложений с оплатой Telegram Stars. Каждый релиз — с "
            "автотестами и деплоем без простоя. GURO ID, в котором вы сейчас "
            "находитесь, — тоже моя работа, можно потрогать вживую."
        ),
        "tech_stack": [
            "Python", "aiogram / python-telegram-bot", "React + Vite",
            "Framer Motion", "aiohttp", "PostgreSQL / SQLite",
            "Telegram Mini Apps", "Telegram Stars",
        ],
        "projects": [
            {
                "name": "GURO ID",
                "tag": "Mini App",
                "description": "Этот самый Mini App: партнёрства, репутация, "
                                "поиск с пейволлом, оплата через Telegram Stars.",
            },
            {
                "name": "Taki Vmeste",
                "tag": "Telegram Bot",
                "description": "Дейтинг-бот с антифрод-верификацией (лицо, жест, "
                                "liveness) — выдерживает ~2.5 регистрации/сек под нагрузкой.",
            },
            {
                "name": "Gambling Community Bot",
                "tag": "Telegram Bot",
                "description": "Тот самый бот, где вы сейчас читаете это — "
                                "скрининг closed-комьюнити, капча, CMS-админка, рассылки.",
            },
            {
                "name": "WorldMusicBot",
                "tag": "Telegram Bot",
                "description": "Музыкальный бот с inline-поиском, скачиванием "
                                "и групповым режимом.",
            },
            {
                "name": "Island Summary Bot",
                "tag": "Telegram Bot",
                "description": "Ежедневные метрики сообщества и live-карта "
                                "участников на сайте.",
            },
        ],
        "contact_url": f"https://t.me/{USERNAME}",
    },
}


def is_showcase_username(username: str | None) -> bool:
    return bool(username) and username.lstrip("@").strip().lower() == USERNAME.lower()
