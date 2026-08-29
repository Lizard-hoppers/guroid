"""SQLite-хранилище анкет с мягкими миграциями (_ensure_column)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import logic

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    vertical TEXT,
    grade TEXT,
    profession TEXT,
    investor_type TEXT,
    investor_amount TEXT,
    investor_needs TEXT,
    request TEXT,
    name TEXT,
    company TEXT,
    linkedin TEXT,
    created_at TEXT,
    sheet_synced INTEGER DEFAULT 0
);
-- 29.08.2026, аудит производительности — 898 строк и НИ ОДНОГО индекса;
-- get_profile(user_id) (вызывается практически отовсюду, включая ГОРЯЧИЙ
-- путь GURO ID directory-поиска) был полным сканом таблицы на каждый
-- вызов. Составной (user_id, id), не просто (user_id) — покрывает и
-- одиночный get_profile (ORDER BY id DESC LIMIT 1 на user_id), и bulk-
-- версию для directory-скана (guro_storage.bulk_latest_profiles_by_id) —
-- та берёт MAX(id) на КАЖДОГО user_id разом; с одиночным индексом это
-- было "SCAN + TEMP B-TREE FOR GROUP BY" (12мс/898 строк), с составным —
-- "SCAN USING COVERING INDEX" без временной сортировки (7мс), и это цена
-- ОДИН раз за весь скан, не за каждого кандидата.
CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON profiles(user_id, id);

CREATE TABLE IF NOT EXISTS button_settings (
    key TEXT PRIMARY KEY,
    text TEXT
);

CREATE TABLE IF NOT EXISTS content_texts (
    key TEXT PRIMARY KEY,
    text TEXT
);

CREATE TABLE IF NOT EXISTS media_assets (
    key TEXT PRIMARY KEY,
    file_id TEXT,
    media_type TEXT
);

CREATE TABLE IF NOT EXISTS menu_buttons (
    slot INTEGER PRIMARY KEY,
    label TEXT,
    url TEXT,
    style TEXT,
    emoji_id TEXT,
    enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS group_mutes (
    chat_id INTEGER,
    user_id INTEGER,
    muted_at TEXT,
    prompt_msg_id INTEGER,
    PRIMARY KEY (chat_id, user_id)
);

-- Перманентный бан администратором (через /admin -> Пользователи), ОТДЕЛЬНО
-- от group_mutes (мут гейта за отсутствие анкеты). Разделение принципиально:
-- заполнение анкеты автоматически снимает мут гейта (unmute_after_profile),
-- но НЕ должно снимать бан — иначе забаненный человек мог бы выйти-зайти в
-- группу (гейт замутит его снова и запишет в group_mutes) и, заполнив
-- анкету, случайно вернуть себе доступ в обход бана.
CREATE TABLE IF NOT EXISTS banned_users (
    user_id INTEGER PRIMARY KEY,
    banned_at TEXT
);

CREATE TABLE IF NOT EXISTS app_flags (
    key TEXT PRIMARY KEY,
    value INTEGER
);

CREATE TABLE IF NOT EXISTS news_seen (
    guid TEXT PRIMARY KEY,
    source TEXT,
    url TEXT,
    seen_at TEXT
);

CREATE TABLE IF NOT EXISTS news_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT,
    source TEXT,
    url TEXT,
    title TEXT,
    text TEXT,
    image_url TEXT,
    status TEXT DEFAULT 'pending',
    admin_chat_id INTEGER,
    admin_msg_id INTEGER,
    created_at TEXT,
    published_at TEXT
);

-- По одному черновику новости уведомляются ВСЕ админы (settings.admin_ids) —
-- каждому своя копия сообщения, отслеживается отдельной строкой, чтобы при
-- решении (публикация/отклонение) можно было убрать копию у КАЖДОГО, а не
-- только у того, кто нажал кнопку (news_drafts.admin_chat_id/admin_msg_id —
-- легаси на одну колонку, перезаписывался последним админом в цикле рассылки).
CREATE TABLE IF NOT EXISTS news_admin_messages (
    draft_id INTEGER,
    admin_chat_id INTEGER,
    admin_msg_id INTEGER,
    PRIMARY KEY (draft_id, admin_chat_id)
);

CREATE TABLE IF NOT EXISTS gossip_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submitter_id INTEGER,
    submitter_username TEXT,
    raw_text TEXT,
    text TEXT,
    flagged INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    admin_chat_id INTEGER,
    admin_msg_id INTEGER,
    created_at TEXT,
    published_at TEXT
);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    action TEXT,
    detail TEXT,
    created_at TEXT
);

-- Реф-система: слот создаётся пригласившим (referrer_id, порядковый slot —
-- 1,2,3...) и выдаёт ссылку `?start=ref_<referrer_id>_<slot>`. Слот считается
-- одноразовым: invited_user_id проставляется первому, кто зашёл по этой
-- ссылке (WHERE invited_user_id IS NULL в consume_referral_link), повторные
-- попытки по той же ссылке игнорируются. «В ответе за приглашённого» —
-- get_referrer_of()/list_invited_by() дают админу видимость связи при бане.
CREATE TABLE IF NOT EXISTS referral_links (
    referrer_id INTEGER,
    slot INTEGER,
    invited_user_id INTEGER,
    invited_username TEXT,
    created_at TEXT,
    used_at TEXT,
    PRIMARY KEY (referrer_id, slot)
);

-- Clean Chat в группе: один активный слот на (chat_id, category) —
-- новое сообщение этой категории (приветствие, реф-подтверждение...)
-- удаляет предыдущее вместо накопления. В отличие от TTL-таймера, слот
-- в БД переживает рестарт бота.
CREATE TABLE IF NOT EXISTS group_singleton_messages (
    chat_id INTEGER,
    category TEXT,
    message_id INTEGER,
    PRIMARY KEY (chat_id, category)
);

-- Пул видео для приветствия в группе (разнообразие вместо одного статичного
-- CMS-медиа) — round-robin по кругу, курсор хранится в app_flags как int
-- (get_int_flag/set_int_flag, НЕ get_flag/set_flag — те приводят к bool).
CREATE TABLE IF NOT EXISTS greeting_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT,
    media_type TEXT DEFAULT 'video',
    added_at TEXT
);
"""


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        self._conn.executescript(_SCHEMA)
        # мягкие миграции — никогда не полагаемся на ручной ALTER TABLE
        for col, ddl in (
            ("investor_type", "TEXT"),
            ("investor_amount", "TEXT"),
            ("investor_needs", "TEXT"),
            ("sheet_synced", "INTEGER DEFAULT 0"),
            ("contacted", "INTEGER DEFAULT 0"),
            ("blocked", "INTEGER DEFAULT 0"),
            ("country", "TEXT"),
            ("country_iso2", "TEXT"),
            ("lang", "TEXT"),
        ):
            self._ensure_column("profiles", col, ddl)
        self._ensure_column("group_mutes", "prompt_msg_id", "INTEGER")
        self._ensure_column("news_drafts", "notified_at", "TEXT")
        self._conn.commit()
        self._seed_menu_buttons()

    def _seed_menu_buttons(self) -> None:
        """Заполняет panel-кнопки дефолтами из constants при первом запуске (если пусто)."""
        import constants as C

        have = self._conn.execute("SELECT COUNT(*) FROM menu_buttons").fetchone()[0]
        if have:
            return
        for b in C.MENU_BUTTON_DEFAULTS:
            self._conn.execute(
                "INSERT INTO menu_buttons (slot, label, url, style, emoji_id, enabled) "
                "VALUES (?,?,?,?,?,1)",
                (b["slot"], b["label"], b["url"], b.get("style"), b.get("emoji_id")),
            )
        self._conn.commit()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        cols = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def save_profile(self, profile: dict) -> tuple[int, str]:
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur = self._conn.execute(
            """
            INSERT INTO profiles (
                user_id, username, vertical, grade, profession,
                investor_type, investor_amount, investor_needs,
                request, name, country, country_iso2, company, linkedin, lang,
                created_at, sheet_synced
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
            """,
            (
                profile.get("user_id"),
                profile.get("username"),
                profile.get("vertical"),
                profile.get("grade"),
                profile.get("profession"),
                profile.get("investor_type"),
                profile.get("investor_amount"),
                profile.get("investor_needs"),
                profile.get("request"),
                profile.get("name"),
                profile.get("country"),
                profile.get("country_iso2"),
                profile.get("company"),
                profile.get("linkedin"),
                profile.get("lang"),
                created_at,
            ),
        )
        self._conn.commit()
        return cur.lastrowid, created_at

    def mark_synced(self, profile_id: int) -> None:
        self._conn.execute(
            "UPDATE profiles SET sheet_synced=1 WHERE id=?", (profile_id,)
        )
        self._conn.commit()

    def has_profile(self, user_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM profiles WHERE user_id=? LIMIT 1", (user_id,)
        ).fetchone()
        return row is not None

    def add_group_mute(self, chat_id: int, user_id: int) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO group_mutes (chat_id, user_id, muted_at) VALUES (?,?,?)",
            (chat_id, user_id, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )
        self._conn.commit()

    def pop_group_mutes(self, user_id: int) -> list[int]:
        """Чаты, где гейт мутил юзера; записи удаляются (одноразовая выдача)."""
        chats = [
            r["chat_id"]
            for r in self._conn.execute(
                "SELECT chat_id FROM group_mutes WHERE user_id=?", (user_id,)
            )
        ]
        if chats:
            self._conn.execute("DELETE FROM group_mutes WHERE user_id=?", (user_id,))
            self._conn.commit()
        return chats

    def ban_user(self, user_id: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO banned_users (user_id, banned_at) VALUES (?,?)",
            (user_id, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )
        self._conn.commit()

    def unban_user(self, user_id: int) -> None:
        self._conn.execute("DELETE FROM banned_users WHERE user_id=?", (user_id,))
        self._conn.commit()

    def is_banned(self, user_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM banned_users WHERE user_id=?", (user_id,)
        ).fetchone()
        return row is not None

    # --- реф-система ---------------------------------------------------

    def create_referral_link(self, referrer_id: int) -> int:
        """Резервирует следующий по счёту слот (1,2,3...) для пригласившего."""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(slot), 0) + 1 FROM referral_links WHERE referrer_id=?",
            (referrer_id,),
        ).fetchone()
        slot = row[0]
        self._conn.execute(
            "INSERT INTO referral_links (referrer_id, slot, created_at) VALUES (?,?,?)",
            (referrer_id, slot, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )
        self._conn.commit()
        return slot

    def consume_referral_link(
        self, referrer_id: int, slot: int, invited_user_id: int, invited_username: str | None,
    ) -> bool:
        """Привязывает слот к первому, кто зашёл по ссылке. False — слот не
        существует или уже использован (повторный /start по старой ссылке)."""
        cur = self._conn.execute(
            "UPDATE referral_links SET invited_user_id=?, invited_username=?, used_at=? "
            "WHERE referrer_id=? AND slot=? AND invited_user_id IS NULL",
            (
                invited_user_id, invited_username,
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                referrer_id, slot,
            ),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_referrer_of(self, user_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM referral_links WHERE invited_user_id=?", (user_id,)
        ).fetchone()

    def list_invited_by(self, referrer_id: int) -> list[sqlite3.Row]:
        return list(self._conn.execute(
            "SELECT * FROM referral_links WHERE referrer_id=? AND invited_user_id IS NOT NULL "
            "ORDER BY slot",
            (referrer_id,),
        ))

    # --- Clean Chat в группе (один активный слот на тип сообщения) --------

    def get_singleton_message(self, chat_id: int, category: str) -> int | None:
        row = self._conn.execute(
            "SELECT message_id FROM group_singleton_messages WHERE chat_id=? AND category=?",
            (chat_id, category),
        ).fetchone()
        return row["message_id"] if row else None

    def set_singleton_message(self, chat_id: int, category: str, message_id: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO group_singleton_messages (chat_id, category, message_id) "
            "VALUES (?,?,?)",
            (chat_id, category, message_id),
        )
        self._conn.commit()

    def set_gate_prompt(self, chat_id: int, user_id: int, msg_id: int) -> None:
        self._conn.execute(
            "UPDATE group_mutes SET prompt_msg_id=? WHERE chat_id=? AND user_id=?",
            (msg_id, chat_id, user_id),
        )
        self._conn.commit()

    def pop_gate_prompts(self, user_id: int) -> list[tuple[int, int]]:
        """(chat_id, msg_id) просьб «пройди анкету»; отметки очищаются сразу."""
        rows = [
            (r["chat_id"], r["prompt_msg_id"])
            for r in self._conn.execute(
                "SELECT chat_id, prompt_msg_id FROM group_mutes "
                "WHERE user_id=? AND prompt_msg_id IS NOT NULL",
                (user_id,),
            )
        ]
        if rows:
            self._conn.execute(
                "UPDATE group_mutes SET prompt_msg_id=NULL WHERE user_id=?", (user_id,)
            )
            self._conn.commit()
        return rows

    def get_gate_prompt(self, chat_id: int, user_id: int) -> int | None:
        """Читает prompt_msg_id БЕЗ очистки — для TTL-удаления: проверить, что
        это ещё тот же промпт (а не новый/уже снятый через /start)."""
        row = self._conn.execute(
            "SELECT prompt_msg_id FROM group_mutes WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
        return row["prompt_msg_id"] if row else None

    def clear_gate_prompt(self, chat_id: int, user_id: int) -> None:
        """Снимает ТОЛЬКО отметку о промпте (мут остаётся) — вызывается после
        TTL-удаления сообщения, чтобы pop_gate_prompts не пытался стереть его
        повторно, когда юзер всё-таки дойдёт до /start."""
        self._conn.execute(
            "UPDATE group_mutes SET prompt_msg_id=NULL WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        )
        self._conn.commit()

    def all_group_mutes(self) -> list[tuple[int, int, int | None]]:
        return [
            (r["chat_id"], r["user_id"], r["prompt_msg_id"])
            for r in self._conn.execute(
                "SELECT chat_id, user_id, prompt_msg_id FROM group_mutes"
            )
        ]

    def clear_group_mutes(self) -> None:
        self._conn.execute("DELETE FROM group_mutes")
        self._conn.commit()

    # --- флаги режимов (тумблеры в /admin) ---
    def get_flag(self, key: str, default: bool = False) -> bool:
        row = self._conn.execute(
            "SELECT value FROM app_flags WHERE key=?", (key,)
        ).fetchone()
        return bool(row["value"]) if row is not None else default

    def set_flag(self, key: str, value: bool) -> None:
        self._conn.execute(
            "INSERT INTO app_flags (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, int(value)),
        )
        self._conn.commit()

    def get_int_flag(self, key: str, default: int = 0) -> int:
        """Как get_flag, но без приведения к bool — для счётчиков/курсоров."""
        row = self._conn.execute(
            "SELECT value FROM app_flags WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row is not None else default

    def set_int_flag(self, key: str, value: int) -> None:
        self._conn.execute(
            "INSERT INTO app_flags (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self._conn.commit()

    # --- пул видео приветствия в группе (разнообразие, round-robin) -------

    def greeting_video_add(self, file_id: str, media_type: str = "video") -> int:
        cur = self._conn.execute(
            "INSERT INTO greeting_videos (file_id, media_type, added_at) VALUES (?,?,?)",
            (file_id, media_type, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )
        self._conn.commit()
        return cur.lastrowid

    def greeting_video_list(self) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT * FROM greeting_videos ORDER BY id"))

    def greeting_video_clear(self) -> None:
        self._conn.execute("DELETE FROM greeting_videos")
        self._conn.commit()

    def greeting_video_next(self) -> tuple[str, str] | None:
        """Следующее видео по кругу (round-robin) — курсор продвигается при
        каждом вызове. None — пул пуст, вызывающий код падает на CMS-медиа."""
        rows = self.greeting_video_list()
        if not rows:
            return None
        idx = self.get_int_flag("greeting_video_cursor", 0) % len(rows)
        self.set_int_flag("greeting_video_cursor", idx + 1)
        row = rows[idx]
        return row["file_id"], row["media_type"]

    # --- новости индустрии (RSS -> GPT -> модерация -> публикация) ---

    def news_is_seen(self, guid: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM news_seen WHERE guid=?", (guid,)
        ).fetchone()
        return row is not None

    def news_mark_seen(self, guid: str, source: str, url: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO news_seen (guid, source, url, seen_at) VALUES (?,?,?,?)",
            (guid, source, url, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )
        self._conn.commit()

    def news_save_draft(self, guid: str, source: str, url: str, title: str,
                        text: str, image_url: str | None) -> int:
        cur = self._conn.execute(
            "INSERT INTO news_drafts (guid, source, url, title, text, image_url, "
            "status, created_at) VALUES (?,?,?,?,?,?,'pending',?)",
            (guid, source, url, title, text, image_url,
             datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )
        self._conn.commit()
        return cur.lastrowid

    def news_add_admin_msg(self, draft_id: int, chat_id: int, msg_id: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO news_admin_messages (draft_id, admin_chat_id, admin_msg_id) "
            "VALUES (?,?,?)",
            (draft_id, chat_id, msg_id),
        )
        self._conn.commit()

    def news_list_admin_msgs(self, draft_id: int) -> list[sqlite3.Row]:
        return list(self._conn.execute(
            "SELECT * FROM news_admin_messages WHERE draft_id=?", (draft_id,)
        ))

    def news_clear_admin_msgs(self, draft_id: int) -> None:
        self._conn.execute("DELETE FROM news_admin_messages WHERE draft_id=?", (draft_id,))
        self._conn.commit()

    def news_get_draft(self, draft_id: int):
        return self._conn.execute(
            "SELECT * FROM news_drafts WHERE id=?", (draft_id,)
        ).fetchone()

    def news_set_status(self, draft_id: int, status: str, published: bool = False) -> None:
        if published:
            self._conn.execute(
                "UPDATE news_drafts SET status=?, published_at=? WHERE id=?",
                (status, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), draft_id),
            )
        else:
            self._conn.execute(
                "UPDATE news_drafts SET status=? WHERE id=?", (status, draft_id)
            )
        self._conn.commit()

    def news_pending_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM news_drafts WHERE status='pending'"
        ).fetchone()
        return row["n"]

    def news_notified_today_count(self) -> int:
        """Сколько черновиков уже разослано админам сегодня (UTC) — дневной лимит."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM news_drafts "
            "WHERE notified_at IS NOT NULL AND date(notified_at) = date('now')"
        ).fetchone()
        return row["n"]

    def news_pending_unnotified(self, limit: int) -> list[sqlite3.Row]:
        """Черновики, ещё не показанные ни одному админу — старые первыми
        (fair queue, а не последние по времени создания)."""
        return list(self._conn.execute(
            "SELECT * FROM news_drafts WHERE status='pending' AND notified_at IS NULL "
            "ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ))

    def news_mark_notified(self, draft_id: int) -> None:
        self._conn.execute(
            "UPDATE news_drafts SET notified_at=? WHERE id=?",
            (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), draft_id),
        )
        self._conn.commit()

    # --- сплетни/инсайды от участников (текст -> GPT -> модерация -> публикация) ---

    def gossip_save_draft(self, submitter_id: int, submitter_username: str,
                          raw_text: str, text: str, flagged: bool = False) -> int:
        cur = self._conn.execute(
            "INSERT INTO gossip_drafts (submitter_id, submitter_username, raw_text, "
            "text, flagged, status, created_at) VALUES (?,?,?,?,?,'pending',?)",
            (submitter_id, submitter_username, raw_text, text, int(flagged),
             datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )
        self._conn.commit()
        return cur.lastrowid

    def gossip_set_admin_msg(self, draft_id: int, chat_id: int, msg_id: int) -> None:
        self._conn.execute(
            "UPDATE gossip_drafts SET admin_chat_id=?, admin_msg_id=? WHERE id=?",
            (chat_id, msg_id, draft_id),
        )
        self._conn.commit()

    def gossip_get_draft(self, draft_id: int):
        return self._conn.execute(
            "SELECT * FROM gossip_drafts WHERE id=?", (draft_id,)
        ).fetchone()

    def gossip_set_status(self, draft_id: int, status: str, published: bool = False) -> None:
        if published:
            self._conn.execute(
                "UPDATE gossip_drafts SET status=?, published_at=? WHERE id=?",
                (status, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), draft_id),
            )
        else:
            self._conn.execute(
                "UPDATE gossip_drafts SET status=? WHERE id=?", (status, draft_id)
            )
        self._conn.commit()

    def gossip_pending_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM gossip_drafts WHERE status='pending'"
        ).fetchone()
        return row["n"]

    def gossip_last_submission_at(self, user_id: int) -> str | None:
        row = self._conn.execute(
            "SELECT created_at FROM gossip_drafts WHERE submitter_id=? "
            "ORDER BY id DESC LIMIT 1", (user_id,),
        ).fetchone()
        return row["created_at"] if row else None

    def unsynced(self) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM profiles WHERE sheet_synced=0 ORDER BY id"
            )
        )

    def all_profiles(self) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT * FROM profiles ORDER BY id"))

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]

    def count_since(self, hours: int) -> int:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM profiles WHERE created_at>=?", (since,)
        ).fetchone()
        return row["n"]

    def get_profile(self, profile_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM profiles WHERE id=?", (profile_id,)
        ).fetchone()

    def get_profile_by_telegram_id(self, user_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM profiles WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)
        ).fetchone()

    def profiles_page(self, offset: int, limit: int) -> list[sqlite3.Row]:
        return list(self._conn.execute(
            "SELECT * FROM profiles ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        ))

    def search_profiles(self, query: str, limit: int = 20) -> list[sqlite3.Row]:
        q = query.strip().lstrip("@")
        like = f"%{q}%"
        rows = self._conn.execute(
            "SELECT * FROM profiles WHERE "
            "CAST(user_id AS TEXT)=? OR CAST(id AS TEXT)=? OR "
            "username LIKE ? OR name LIKE ? OR vertical LIKE ? OR company LIKE ? "
            "ORDER BY id DESC LIMIT ?",
            (q, q, like, like, like, like, limit),
        )
        return list(rows)

    def set_contacted(self, profile_id: int, value: bool) -> None:
        self._conn.execute(
            "UPDATE profiles SET contacted=? WHERE id=?", (int(value), profile_id)
        )
        self._conn.commit()

    def mark_blocked(self, user_id: int) -> None:
        self._conn.execute(
            "UPDATE profiles SET blocked=1 WHERE user_id=?", (user_id,)
        )
        self._conn.commit()

    def user_mute_chats(self, user_id: int) -> list[int]:
        """Чаты, где юзер сейчас замучен гейтом (не удаляет записи, в отличие от pop_group_mutes)."""
        return [
            r["chat_id"] for r in self._conn.execute(
                "SELECT chat_id FROM group_mutes WHERE user_id=?", (user_id,)
            )
        ]

    def profiles_for_broadcast(self, vertical: str | None = None,
                               grade: str | None = None,
                               country: str | None = None,
                               country_in: list[str] | None = None) -> list[sqlite3.Row]:
        """Уникальные (user_id, username) анкет, подходящих под фильтр, без заблокировавших бота."""
        sql = "SELECT DISTINCT user_id, username FROM profiles WHERE blocked=0"
        params: list = []
        if vertical:
            sql += " AND vertical=?"
            params.append(vertical)
        if grade:
            sql += " AND grade=?"
            params.append(grade)
        if country:
            sql += " AND country=?"
            params.append(country)
        if country_in:
            sql += f" AND country IN ({','.join('?' for _ in country_in)})"
            params.extend(country_in)
        return list(self._conn.execute(sql, params))

    def country_broadcast_segments(self) -> list[sqlite3.Row]:
        """(country, country_iso2, n) — сегменты для рассылки по странам.

        n — кол-во УНИКАЛЬНЫХ user_id с этой страной, без заблокировавших
        бота; страна должна быть нормализована (непустая)."""
        return list(self._conn.execute(
            "SELECT country, country_iso2, COUNT(DISTINCT user_id) AS n FROM profiles "
            "WHERE blocked=0 AND country IS NOT NULL AND TRIM(country) != '' "
            "GROUP BY country ORDER BY n DESC, country ASC"
        ))

    def set_profile_country(self, profile_id: int, country: str, country_iso2: str) -> None:
        self._conn.execute(
            "UPDATE profiles SET country=?, country_iso2=? WHERE id=?",
            (country, country_iso2, profile_id),
        )
        self._conn.commit()

    def profiles_needing_country_normalization(self) -> list[sqlite3.Row]:
        """Анкеты со страной, но без iso2 — заполнены до фичи GPT-нормализации."""
        return list(self._conn.execute(
            "SELECT id, country FROM profiles WHERE country IS NOT NULL AND TRIM(country) != '' "
            "AND (country_iso2 IS NULL OR TRIM(country_iso2) = '')"
        ))

    # --- журнал админ-действий -------------------------------------------

    def log_action(self, admin_id: int, action: str, detail: str = "") -> None:
        self._conn.execute(
            "INSERT INTO admin_audit_log (admin_id, action, detail, created_at) "
            "VALUES (?,?,?,?)",
            (admin_id, action, detail,
             datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )
        self._conn.commit()

    def audit_log_page(self, offset: int, limit: int) -> list[sqlite3.Row]:
        return list(self._conn.execute(
            "SELECT * FROM admin_audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ))

    def audit_log_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM admin_audit_log").fetchone()[0]

    def export_csv(self) -> str:
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        headers = [
            "id", "created_at", "user_id", "username", "vertical", "grade",
            "profession", "investor_type", "investor_amount", "investor_needs",
            "request", "name", "country", "company", "linkedin",
        ]
        writer.writerow(headers)
        for r in self.all_profiles():
            writer.writerow([r[h] for h in headers])
        return buf.getvalue()

    # --- CMS: оверрайды кнопок и текстов ---------------------------------

    def get_button_override(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT text FROM button_settings WHERE key=?", (key,)
        ).fetchone()
        return row["text"] if row and row["text"] else None

    def set_button_override(self, key: str, text: str) -> None:
        self._conn.execute(
            """
            INSERT INTO button_settings (key, text) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET text=excluded.text
            """,
            (key, text),
        )
        self._conn.commit()

    def reset_button(self, key: str) -> None:
        self._conn.execute("DELETE FROM button_settings WHERE key=?", (key,))
        self._conn.commit()

    def get_text_override(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT text FROM content_texts WHERE key=?", (key,)
        ).fetchone()
        return row["text"] if row and row["text"] else None

    def set_text_override(self, key: str, text: str) -> None:
        self._conn.execute(
            """
            INSERT INTO content_texts (key, text) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET text=excluded.text
            """,
            (key, text),
        )
        self._conn.commit()

    def reset_text(self, key: str) -> None:
        self._conn.execute("DELETE FROM content_texts WHERE key=?", (key,))
        self._conn.commit()

    def overridden_buttons(self) -> set[str]:
        return {r["key"] for r in self._conn.execute("SELECT key FROM button_settings")}

    def overridden_texts(self) -> set[str]:
        return {r["key"] for r in self._conn.execute("SELECT key FROM content_texts")}

    # --- CMS: медиа экранов ---------------------------------------------

    def get_media(self, key: str) -> tuple[str, str] | None:
        row = self._conn.execute(
            "SELECT file_id, media_type FROM media_assets WHERE key=?", (key,)
        ).fetchone()
        if row and row["file_id"]:
            return row["file_id"], row["media_type"] or "photo"
        return None

    def set_media(self, key: str, file_id: str, media_type: str) -> None:
        self._conn.execute(
            """
            INSERT INTO media_assets (key, file_id, media_type) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET file_id=excluded.file_id,
                                           media_type=excluded.media_type
            """,
            (key, file_id, media_type),
        )
        self._conn.commit()

    def reset_media(self, key: str) -> None:
        self._conn.execute("DELETE FROM media_assets WHERE key=?", (key,))
        self._conn.commit()

    def media_keys(self) -> set[str]:
        return {r["key"] for r in self._conn.execute("SELECT key FROM media_assets")}

    # --- Панель ссылок в группе (menu_buttons) ---------------------------

    def menu_buttons(self, only_enabled: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM menu_buttons"
        if only_enabled:
            sql += " WHERE enabled=1"
        sql += " ORDER BY slot"
        return list(self._conn.execute(sql))

    def get_menu_button(self, slot: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM menu_buttons WHERE slot=?", (slot,)
        ).fetchone()

    def update_menu_button(self, slot: int, **fields) -> None:
        """Частичное обновление: только переданные поля (label/url/style/emoji_id/enabled)."""
        allowed = {"label", "url", "style", "emoji_id", "enabled"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        cols = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(
            f"UPDATE menu_buttons SET {cols} WHERE slot=?",
            (*sets.values(), slot),
        )
        self._conn.commit()

    def reset_menu_button(self, slot: int) -> None:
        """Сброс кнопки к дефолту из constants (label/url, без цвета/эмодзи, enabled)."""
        import constants as C

        default = next((b for b in C.MENU_BUTTON_DEFAULTS if b["slot"] == slot), None)
        if default is None:
            return
        self._conn.execute(
            "UPDATE menu_buttons SET label=?, url=?, style=?, emoji_id=?, enabled=1 WHERE slot=?",
            (default["label"], default["url"], default.get("style"),
             default.get("emoji_id"), slot),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
