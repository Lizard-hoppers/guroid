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
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

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
            openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        )

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids
