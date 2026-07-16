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
        ):
            self._ensure_column("profiles", col, ddl)
        self._ensure_column("group_mutes", "prompt_msg_id", "INTEGER")
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
                request, name, company, linkedin, created_at, sheet_synced
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0)
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
                profile.get("company"),
                profile.get("linkedin"),
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

    def news_set_admin_msg(self, draft_id: int, chat_id: int, msg_id: int) -> None:
        self._conn.execute(
            "UPDATE news_drafts SET admin_chat_id=?, admin_msg_id=? WHERE id=?",
            (chat_id, msg_id, draft_id),
        )
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
                               grade: str | None = None) -> list[sqlite3.Row]:
        """Уникальные (user_id, username) анкет, подходящих под фильтр, без заблокировавших бота."""
        sql = "SELECT DISTINCT user_id, username FROM profiles WHERE blocked=0"
        params: list = []
        if vertical:
            sql += " AND vertical=?"
            params.append(vertical)
        if grade:
            sql += " AND grade=?"
            params.append(grade)
        return list(self._conn.execute(sql, params))

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
            "request", "name", "company", "linkedin",
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
