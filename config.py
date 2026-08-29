"""Конфигурация бота. Все значения берутся из окружения (.env через systemd)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _split_ids(raw: str) -> tuple[int, ...]:
    out = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return tuple(out)


@dataclass
class Settings:
    bot_token: str
    base_dir: Path
    database_path: Path
    admin_ids: tuple[int, ...]
    community_invite_url: str
    google_sheets_enabled: bool
    google_sheets_spreadsheet_id: str
    google_sheets_worksheet_name: str
    google_sheets_credentials_path: Path | None
    # Капча в группе (второй уровень). Поля с дефолтами — чтобы прямой
    # конструктор Settings(...) в тестах не требовал их явно.
    captcha_enabled: bool = True
    captcha_options: int = 4
    captcha_group_ids: tuple[int, ...] = ()
    # Новости индустрии: RSS -> GPT-форматирование -> черновик админу -> публикация.
    news_enabled: bool = False
    news_chat_id: int = 0
    news_topic_id: int | None = None
    gossip_topic_id: int | None = None
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # Группа сообщества (для одноразовых инвайт-ссылок после анкеты). 0 = не настроено,
    # тогда финал использует статичный community_invite_url (как раньше).
    community_chat_id: int = 0
    # Тема (топик) англоязычного чата в том же форуме — приветствие после
    # анкеты на английском уходит туда, а не в основной (СНГ) топик.
    community_en_topic_id: int | None = None
    # GURO ID Mini App: отдельный aiohttp-процесс guro_id_api.py, порт для
    # локального биндинга (наружу — через Apache+TLS, см. OPERATIONS.md).
    guro_id_api_port: int = 8092
    # Публичный HTTPS-адрес Mini App (тот же порт, но снаружи) — ставится
    # Menu Button-ом бота при старте (bot.py post_init).
    guro_id_webapp_url: str = "https://guro-app.193.111.62.16.sslip.io/"
    # CryptoBot (Crypto Pay API) — оплата подписки GURO ID в крипте
    # (альтернатива Stars). Пусто = крипто-оплата выключена (эндпойнты
    # отдают 503), см. guro_crypto.py про получение токена.
    cryptobot_api_token: str = ""
    # 29.08.2026 (владелец: "прикрутить новый ключ, 5 платежей на него и
    # 1 на старый, по кругу") — второй токен/приложение CryptoBot. Новые
    # инвойсы распределяются между cryptobot_api_token_new (вес 5) и
    # cryptobot_api_token (вес 1) кольцом, см. guro_id_api._pick_crypto_
    # token; позиция кольца — персистентный счётчик в guro_config (см.
    # GC.CRYPTO_TOKEN_CYCLE_KEY), переживает рестарт процесса. Вебхук
    # проверяет подпись по ОБОИМ токенам (см. handle_crypto_webhook) — при
    # оплате неизвестно заранее, каким токеном был создан именно этот
    # инвойс. Пусто = ведёт себя как раньше, только cryptobot_api_token.
    cryptobot_api_token_new: str = ""
    # Юзернейм бота без @ — нужен серверу для сборки QR-дипссылок GURO ID
    # (`t.me/<bot_username>?start=guro_<id>`), без лишнего вызова getMe().
    bot_username: str = "GamblingCommunitybot"
    # Ончейн-верификация крипто-хеша сделки (ТЗ 5.4, 25.08.2026, см.
    # guro_chain_verify.py) — НЕ платёжные ключи (те у cryptobot_api_token
    # выше). TRONSCAN необязателен (публичный эндпойнт работает и без
    # ключа), ETHERSCAN/BSCSCAN обязательны — без них верификация для
    # соответствующей сети мягко отключена (verified=False, API_KEY_MISSING).
    tronscan_api_key: str = ""
    etherscan_api_key: str = ""
    bscscan_api_key: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        base = Path(os.environ.get("BASE_DIR", Path(__file__).resolve().parent))
        token = os.environ.get("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("BOT_TOKEN is not set")

        db = os.environ.get("DATABASE_PATH", "").strip()
        database_path = Path(db) if db else base / "gambling_community.sqlite3"

        creds_raw = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH", "").strip()
        creds_path = Path(creds_raw) if creds_raw else None

        return cls(
            bot_token=token,
            base_dir=base,
            database_path=database_path,
            admin_ids=_split_ids(os.environ.get("ADMIN_IDS", "")),
            community_invite_url=os.environ.get(
                "COMMUNITY_INVITE_URL", "https://t.me/GamblingCommunitybot"
            ).strip(),
            google_sheets_enabled=os.environ.get("GOOGLE_SHEETS_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            google_sheets_spreadsheet_id=os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip(),
            google_sheets_worksheet_name=os.environ.get(
                "GOOGLE_SHEETS_WORKSHEET_NAME", "Анкеты"
            ).strip(),
            google_sheets_credentials_path=creds_path,
            captcha_enabled=os.environ.get("CAPTCHA_ENABLED", "true").strip().lower()
            in {"1", "true", "yes", "on"},
            captcha_options=max(2, int(os.environ.get("CAPTCHA_OPTIONS", "4") or 4)),
            captcha_group_ids=_split_ids(os.environ.get("CAPTCHA_GROUP_IDS", "")),
            news_enabled=os.environ.get("NEWS_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            news_chat_id=int(os.environ.get("NEWS_CHAT_ID", "0") or 0),
            news_topic_id=(
                int(os.environ["NEWS_TOPIC_ID"])
                if os.environ.get("NEWS_TOPIC_ID", "").strip()
                else None
            ),
            gossip_topic_id=(
                int(os.environ["GOSSIP_TOPIC_ID"])
                if os.environ.get("GOSSIP_TOPIC_ID", "").strip()
                else None
            ),
            openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            community_chat_id=int(os.environ.get("COMMUNITY_CHAT_ID", "0") or 0),
            community_en_topic_id=(
                int(os.environ["COMMUNITY_EN_TOPIC_ID"])
                if os.environ.get("COMMUNITY_EN_TOPIC_ID", "").strip()
                else None
            ),
            guro_id_api_port=int(os.environ.get("GURO_ID_API_PORT", "8092") or 8092),
            guro_id_webapp_url=os.environ.get(
                "GURO_ID_WEBAPP_URL", "https://guro-app.193.111.62.16.sslip.io/"
            ).strip(),
            cryptobot_api_token=os.environ.get("CRYPTOBOT_API_TOKEN", "").strip(),
            cryptobot_api_token_new=os.environ.get("CRYPTOBOT_API_TOKEN_NEW", "").strip(),
            bot_username=os.environ.get("BOT_USERNAME", "GamblingCommunitybot").strip()
            or "GamblingCommunitybot",
            tronscan_api_key=os.environ.get("TRONSCAN_API_KEY", "").strip(),
            etherscan_api_key=os.environ.get("ETHERSCAN_API_KEY", "").strip(),
            bscscan_api_key=os.environ.get("BSCSCAN_API_KEY", "").strip(),
        )

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids
