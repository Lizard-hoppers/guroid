"""SQLite-хранилище модуля GURO ID (партнёрства/репутация). Пишет в ТОТ ЖЕ
файл gambling_community.sqlite3, что и основной storage.py, но в свои
таблицы — profiles не трогаем. Инстанцируется отдельно в каждом процессе
(bot.py и guro_id_api.py — два процесса, каждому своё соединение)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import guro_constants as GC
import guro_logic as GL

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guro_users (
    user_id INTEGER PRIMARY KEY,
    reputation_score REAL DEFAULT 0,
    subscription_status TEXT DEFAULT 'inactive',
    subscription_expires_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS partnerships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    initiator_id INTEGER,
    confirmer_id INTEGER,
    status TEXT DEFAULT 'pending',
    vertical TEXT,
    geo TEXT,
    counts_toward_rating INTEGER DEFAULT 1,
    visible_publicly INTEGER DEFAULT 1,
    created_at TEXT,
    confirmed_at TEXT
);

-- Личные сообщения внутри прилы (Фаза 1, 11.08.2026). user_a/user_b всегда
-- хранятся в канонической паре (меньший id первым, см. _thread_pair) —
-- один тред на пару людей, независимо от того, кто написал первым.
CREATE TABLE IF NOT EXISTS guro_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_a INTEGER,
    user_b INTEGER,
    initiator_id INTEGER,
    created_at TEXT,
    last_message_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_guro_threads_pair ON guro_threads(user_a, user_b);

CREATE TABLE IF NOT EXISTS guro_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER,
    sender_id INTEGER,
    body TEXT,
    created_at TEXT,
    read_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_guro_messages_thread ON guro_messages(thread_id);

-- Кабинет рекрутера (Фаза 3, 12.08.2026) — САТЕЛЛИТ к guro_users, не
-- трогает его. Рейтинг/партнёрства/базовая подписка GURO ID остаются
-- общими и берутся из guro_users/partnerships как обычно; тут только
-- отдельная витрина (RECRUITER_EXTRA_FIELDS + PRIVACY_FIELDS-тумблеры,
-- добавляются мягкой миграцией ниже) и своя, ОТДЕЛЬНАЯ подписка.
CREATE TABLE IF NOT EXISTS guro_recruiter_profiles (
    user_id INTEGER PRIMARY KEY,
    subscription_status TEXT DEFAULT 'inactive',
    subscription_expires_at TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- Вакансии (Фаза 4, 12.08.2026) — публикует только подписчик кабинета
-- рекрутера (проверяется в guro_id_api.handle_create_vacancy, не тут).
CREATE TABLE IF NOT EXISTS guro_vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER,
    title TEXT,
    vertical TEXT,
    seniority TEXT,
    location TEXT,
    remote INTEGER DEFAULT 0,
    relocation INTEGER DEFAULT 0,
    salary_from REAL,
    salary_to REAL,
    salary_negotiable INTEGER DEFAULT 0,
    description TEXT,
    lang TEXT DEFAULT 'ru',
    status TEXT DEFAULT 'active',
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_guro_vacancies_author ON guro_vacancies(author_id);
CREATE INDEX IF NOT EXISTS idx_guro_vacancies_status_lang ON guro_vacancies(status, lang);

-- Расширение "Моё CV" (12.08.2026) — история изменений должности (для
-- лимита "не чаще 2 раз в год", см. GuroStorage.set_cv_profession) и
-- отдельные записи опыта работы (один человек -> много мест работы).
CREATE TABLE IF NOT EXISTS guro_profession_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    changed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_guro_profession_changes_user ON guro_profession_changes(user_id);

CREATE TABLE IF NOT EXISTS guro_cv_experience (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    company TEXT,
    position TEXT,
    date_from TEXT,
    date_to TEXT,
    location TEXT,
    description TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_guro_cv_experience_user ON guro_cv_experience(user_id);
"""


class GuroStorage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        # WAL — свойство самого файла БД, переживает процесс; включаем один раз,
        # снижает "database is locked" теперь, когда файл пишут 2 процесса
        # (bot.py и guro_id_api.py).
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        # мягкие миграции — never ALTER TABLE вручную (тот же приём, что в storage.py)
        for field in GC.PRIVACY_FIELDS:
            self._ensure_column("guro_users", field, "INTEGER DEFAULT 0")
        for field in GC.EXTRA_PROFILE_FIELDS:
            self._ensure_column("guro_users", field, "TEXT")
        self._ensure_column("guro_users", "work_status", "TEXT")
        # Фаза 2 (11.08.2026) — офер/суммы/отзыв в форме подтверждения
        # партнёрства (см. PDF-фидбек владельца). amount_visible=0 по
        # умолчанию (суммы приватны, owner решает при создании — opt-in,
        # тот же принцип, что PRIVACY_FIELDS), offer/review публичны всегда
        # (это и есть смысл "проверить репутацию контакта").
        self._ensure_column("partnerships", "offer", "TEXT")
        self._ensure_column("partnerships", "amount_received", "REAL")
        self._ensure_column("partnerships", "amount_paid", "REAL")
        self._ensure_column("partnerships", "review", "TEXT")
        self._ensure_column("partnerships", "amount_visible", "INTEGER DEFAULT 0")
        # Фаза 3 (12.08.2026) — витрина кабинета рекрутера, тот же набор
        # тумблеров приватности, что у личного профиля (PRIVACY_FIELDS),
        # применённый к ДРУГОЙ таблице — коллизий нет.
        for field in GC.RECRUITER_EXTRA_FIELDS:
            self._ensure_column("guro_recruiter_profiles", field, "TEXT")
        for field in GC.PRIVACY_FIELDS:
            self._ensure_column("guro_recruiter_profiles", field, "INTEGER DEFAULT 0")
        # Расширение "Моё CV" (12.08.2026) — новые поля личного профиля,
        # гейтятся существующим show_cv (см. guro_constants.CV_SIMPLE_FIELDS).
        self._ensure_column("guro_users", "cv_profession", "TEXT")
        for field in GC.CV_SIMPLE_FIELDS:
            self._ensure_column("guro_users", field, "TEXT")
        self._ensure_column("guro_users", "cv_grade", "TEXT")
        self._ensure_column("guro_users", "cv_relocation_ready", "INTEGER")
        self._ensure_column("guro_users", "cv_polygraph_consent", "INTEGER")
        self._ensure_column("guro_users", "cv_salary_from", "REAL")
        self._ensure_column("guro_users", "cv_salary_to", "REAL")
        self._ensure_column("guro_users", "cv_salary_negotiable", "INTEGER DEFAULT 0")
        self._conn.commit()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        cols = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _now_str() -> str:
        return GL.format_db_datetime(GuroStorage._now())

    # --- profiles (только чтение, таблица чужая) ------------------------

    def get_profile(self, user_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM profiles WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)
        ).fetchone()

    def find_profile_by_username(self, username: str) -> sqlite3.Row | None:
        username = username.lstrip("@").strip().lower()
        if not username:
            return None
        return self._conn.execute(
            "SELECT * FROM profiles WHERE LOWER(username)=? ORDER BY id DESC LIMIT 1",
            (username,),
        ).fetchone()

    # --- guro_users -------------------------------------------------------

    def get_or_create_guro_user(self, user_id: int) -> sqlite3.Row:
        row = self._conn.execute("SELECT * FROM guro_users WHERE user_id=?", (user_id,)).fetchone()
        if row is not None:
            return row
        profile = self.get_profile(user_id)
        created_at = GL.parse_db_datetime(profile["created_at"]) if profile else None
        score = GL.initial_reputation(created_at, self._now())
        self._conn.execute(
            "INSERT INTO guro_users (user_id, reputation_score, updated_at) VALUES (?,?,?)",
            (user_id, score, self._now_str()),
        )
        self._conn.commit()
        return self._conn.execute("SELECT * FROM guro_users WHERE user_id=?", (user_id,)).fetchone()

    def get_subscription(self, user_id: int) -> tuple[str, datetime | None]:
        row = self.get_or_create_guro_user(user_id)
        return row["subscription_status"], GL.parse_db_datetime(row["subscription_expires_at"])

    def is_subscribed(self, user_id: int) -> bool:
        status, expires_at = self.get_subscription(user_id)
        return GL.subscription_active(status, expires_at, self._now())

    def list_guro_user_ids(self) -> list[int]:
        """Для периодической синхронизации статус-тегов (guro_tags_sync.py) —
        только те, кто хоть раз коснулся GURO ID, не вся группа."""
        rows = self._conn.execute("SELECT user_id FROM guro_users").fetchall()
        return [row["user_id"] for row in rows]

    def activate_subscription(self, user_id: int, duration_days: int) -> str:
        self.get_or_create_guro_user(user_id)
        expires_at = GL.subscription_expires_at(self._now(), duration_days)
        self._conn.execute(
            "UPDATE guro_users SET subscription_status=?, subscription_expires_at=?, updated_at=? "
            "WHERE user_id=?",
            (GC.SUBSCRIPTION_ACTIVE, GL.format_db_datetime(expires_at), self._now_str(), user_id),
        )
        self._conn.commit()
        return GL.format_db_datetime(expires_at)

    def get_privacy(self, user_id: int) -> dict:
        row = self.get_or_create_guro_user(user_id)
        return {field: bool(row[field]) for field in GC.PRIVACY_FIELDS}

    def set_privacy_field(self, user_id: int, field: str, value: bool) -> dict:
        """Поднимает ValueError('UNKNOWN_FIELD') на неизвестное поле — так
        обработчик API отличит опечатку/чужой ключ от валидного запроса."""
        if field not in GC.PRIVACY_FIELDS:
            raise ValueError("UNKNOWN_FIELD")
        self.get_or_create_guro_user(user_id)
        self._conn.execute(
            f"UPDATE guro_users SET {field}=?, updated_at=? WHERE user_id=?",
            (1 if value else 0, self._now_str(), user_id),
        )
        self._conn.commit()
        return self.get_privacy(user_id)

    def get_extra_profile(self, user_id: int) -> dict:
        row = self.get_or_create_guro_user(user_id)
        return {field: row[field] for field in GC.EXTRA_PROFILE_FIELDS}

    def set_extra_profile_field(self, user_id: int, field: str, value: str) -> dict:
        """Поднимает ValueError('UNKNOWN_FIELD') на неизвестное поле — тот
        же приём, что и set_privacy_field."""
        if field not in GC.EXTRA_PROFILE_FIELDS:
            raise ValueError("UNKNOWN_FIELD")
        self.get_or_create_guro_user(user_id)
        self._conn.execute(
            f"UPDATE guro_users SET {field}=?, updated_at=? WHERE user_id=?",
            (value, self._now_str(), user_id),
        )
        self._conn.commit()
        return self.get_extra_profile(user_id)

    def get_work_status(self, user_id: int) -> str | None:
        row = self.get_or_create_guro_user(user_id)
        return row["work_status"]

    def set_work_status(self, user_id: int, value: str | None) -> str | None:
        """Поднимает ValueError('INVALID_STATUS') на значение вне
        GC.WORK_STATUS_VALUES — None (== "выкл"/скрыто) всегда разрешён."""
        if value is not None and value not in GC.WORK_STATUS_VALUES:
            raise ValueError("INVALID_STATUS")
        self.get_or_create_guro_user(user_id)
        self._conn.execute(
            "UPDATE guro_users SET work_status=?, updated_at=? WHERE user_id=?",
            (value, self._now_str(), user_id),
        )
        self._conn.commit()
        return self.get_work_status(user_id)

    # --- кабинет рекрутера (Фаза 3, 12.08.2026) --------------------------

    def get_or_create_recruiter_profile(self, user_id: int) -> sqlite3.Row:
        row = self._conn.execute(
            "SELECT * FROM guro_recruiter_profiles WHERE user_id=?", (user_id,)
        ).fetchone()
        if row is not None:
            return row
        self._conn.execute(
            "INSERT INTO guro_recruiter_profiles (user_id, created_at, updated_at) VALUES (?,?,?)",
            (user_id, self._now_str(), self._now_str()),
        )
        self._conn.commit()
        return self._conn.execute(
            "SELECT * FROM guro_recruiter_profiles WHERE user_id=?", (user_id,)
        ).fetchone()

    def is_recruiter_subscribed(self, user_id: int) -> bool:
        row = self._conn.execute(
            "SELECT subscription_status, subscription_expires_at FROM guro_recruiter_profiles WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if row is None:
            return False
        return GL.subscription_active(
            row["subscription_status"], GL.parse_db_datetime(row["subscription_expires_at"]), self._now(),
        )

    def activate_recruiter_subscription(self, user_id: int, duration_days: int) -> str:
        self.get_or_create_recruiter_profile(user_id)
        expires_at = GL.subscription_expires_at(self._now(), duration_days)
        self._conn.execute(
            "UPDATE guro_recruiter_profiles SET subscription_status=?, subscription_expires_at=?, "
            "updated_at=? WHERE user_id=?",
            (GC.SUBSCRIPTION_ACTIVE, GL.format_db_datetime(expires_at), self._now_str(), user_id),
        )
        self._conn.commit()
        return GL.format_db_datetime(expires_at)

    def get_recruiter_extra(self, user_id: int) -> dict:
        row = self.get_or_create_recruiter_profile(user_id)
        return {field: row[field] for field in GC.RECRUITER_EXTRA_FIELDS}

    def set_recruiter_extra_field(self, user_id: int, field: str, value: str | None) -> dict:
        """Поднимает ValueError('UNKNOWN_FIELD') — тот же приём, что и
        set_extra_profile_field у личного профиля."""
        if field not in GC.RECRUITER_EXTRA_FIELDS:
            raise ValueError("UNKNOWN_FIELD")
        self.get_or_create_recruiter_profile(user_id)
        self._conn.execute(
            f"UPDATE guro_recruiter_profiles SET {field}=?, updated_at=? WHERE user_id=?",
            (value, self._now_str(), user_id),
        )
        self._conn.commit()
        return self.get_recruiter_extra(user_id)

    def get_recruiter_privacy(self, user_id: int) -> dict:
        row = self.get_or_create_recruiter_profile(user_id)
        return {field: bool(row[field]) for field in GC.PRIVACY_FIELDS}

    def set_recruiter_privacy_field(self, user_id: int, field: str, value: bool) -> dict:
        if field not in GC.PRIVACY_FIELDS:
            raise ValueError("UNKNOWN_FIELD")
        self.get_or_create_recruiter_profile(user_id)
        self._conn.execute(
            f"UPDATE guro_recruiter_profiles SET {field}=?, updated_at=? WHERE user_id=?",
            (1 if value else 0, self._now_str(), user_id),
        )
        self._conn.commit()
        return self.get_recruiter_privacy(user_id)

    # --- partnerships -------------------------------------------------------

    def count_confirmed_partnerships(self, user_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM partnerships WHERE status=? AND (initiator_id=? OR confirmer_id=?)",
            (GC.PARTNERSHIP_STATUS_CONFIRMED, user_id, user_id),
        ).fetchone()
        return row["n"]

    def list_confirmed_partnerships(self, user_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM partnerships WHERE status=? AND (initiator_id=? OR confirmer_id=?) "
            "AND visible_publicly=1 ORDER BY confirmed_at DESC",
            (GC.PARTNERSHIP_STATUS_CONFIRMED, user_id, user_id),
        ).fetchall()

    def _last_request_between(self, user_a: int, user_b: int) -> datetime | None:
        row = self._conn.execute(
            "SELECT MAX(created_at) AS latest FROM partnerships WHERE "
            "(initiator_id=? AND confirmer_id=?) OR (initiator_id=? AND confirmer_id=?)",
            (user_a, user_b, user_b, user_a),
        ).fetchone()
        return GL.parse_db_datetime(row["latest"]) if row else None

    def create_partnership(
        self, initiator_id: int, confirmer_id: int, vertical: str | None, geo: str | None,
        *, offer: str | None = None, amount_received: float | None = None,
        amount_paid: float | None = None, review: str | None = None, amount_visible: bool = False,
    ) -> sqlite3.Row:
        """Поднимает ValueError с понятным кодом-строкой при нарушении правил
        (see ТЗ п.4/п.8): NO_CONFIRMER_PROFILE / SELF_PARTNERSHIP / RATE_LIMITED.
        offer/amount_*/review/amount_visible (Фаза 2, 11.08.2026) — заполняет
        ТОЛЬКО инициатор в момент создания заявки; confirmer лишь
        подтверждает/отклоняет кнопкой, отдельной формы у него нет (см. план)."""
        if initiator_id == confirmer_id:
            raise ValueError("SELF_PARTNERSHIP")
        confirmer_profile = self.get_profile(confirmer_id)
        if confirmer_profile is None:
            # Bot API не может написать юзеру, который никогда не писал боту.
            raise ValueError("NO_CONFIRMER_PROFILE")

        now = self._now()
        if GL.rate_limited(self._last_request_between(initiator_id, confirmer_id), now):
            raise ValueError("RATE_LIMITED")

        initiator_profile = self.get_profile(initiator_id)
        counts = GL.counts_toward_rating(
            GL.parse_db_datetime(initiator_profile["created_at"]) if initiator_profile else None,
            GL.parse_db_datetime(confirmer_profile["created_at"]),
            now,
        )
        cur = self._conn.execute(
            "INSERT INTO partnerships (initiator_id, confirmer_id, status, vertical, geo, "
            "counts_toward_rating, created_at, offer, amount_received, amount_paid, review, "
            "amount_visible) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (initiator_id, confirmer_id, GC.PARTNERSHIP_STATUS_PENDING, vertical, geo,
             1 if counts else 0, GL.format_db_datetime(now), offer, amount_received, amount_paid,
             review, 1 if amount_visible else 0),
        )
        self._conn.commit()
        return self._conn.execute("SELECT * FROM partnerships WHERE id=?", (cur.lastrowid,)).fetchone()

    def get_partnership(self, partnership_id: int) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM partnerships WHERE id=?", (partnership_id,)).fetchone()

    def respond_partnership(self, partnership_id: int, responder_id: int, accept: bool) -> sqlite3.Row:
        """Поднимает ValueError: NOT_FOUND / NOT_YOUR_REQUEST / ALREADY_RESOLVED."""
        row = self.get_partnership(partnership_id)
        if row is None:
            raise ValueError("NOT_FOUND")
        if row["confirmer_id"] != responder_id:
            raise ValueError("NOT_YOUR_REQUEST")
        if row["status"] != GC.PARTNERSHIP_STATUS_PENDING:
            raise ValueError("ALREADY_RESOLVED")

        if not accept:
            self._conn.execute(
                "UPDATE partnerships SET status=? WHERE id=?",
                (GC.PARTNERSHIP_STATUS_DECLINED, partnership_id),
            )
            self._conn.commit()
            return self.get_partnership(partnership_id)

        now = self._now()
        a = self.get_or_create_guro_user(row["initiator_id"])
        b = self.get_or_create_guro_user(row["confirmer_id"])
        if row["counts_toward_rating"]:
            new_a = a["reputation_score"] + GL.confirmation_gain()
            new_b = b["reputation_score"] + GL.confirmation_gain()
            self._conn.execute(
                "UPDATE guro_users SET reputation_score=?, updated_at=? WHERE user_id=?",
                (new_a, self._now_str(), row["initiator_id"]),
            )
            self._conn.execute(
                "UPDATE guro_users SET reputation_score=?, updated_at=? WHERE user_id=?",
                (new_b, self._now_str(), row["confirmer_id"]),
            )
        self._conn.execute(
            "UPDATE partnerships SET status=?, confirmed_at=? WHERE id=?",
            (GC.PARTNERSHIP_STATUS_CONFIRMED, GL.format_db_datetime(now), partnership_id),
        )
        self._conn.commit()
        return self.get_partnership(partnership_id)

    # --- личные сообщения (Фаза 1, 11.08.2026) ---------------------------

    @staticmethod
    def _thread_pair(user_a: int, user_b: int) -> tuple[int, int]:
        return (user_a, user_b) if user_a <= user_b else (user_b, user_a)

    def find_thread(self, user_a: int, user_b: int) -> sqlite3.Row | None:
        lo, hi = self._thread_pair(user_a, user_b)
        return self._conn.execute(
            "SELECT * FROM guro_threads WHERE user_a=? AND user_b=?", (lo, hi)
        ).fetchone()

    def list_threads(self, user_id: int) -> list[dict]:
        """Треды пользователя, самые свежие сверху, с превью последнего
        сообщения и счётчиком непрочитанных ИМ (не всего в треде)."""
        rows = self._conn.execute(
            "SELECT * FROM guro_threads WHERE user_a=? OR user_b=? ORDER BY last_message_at DESC",
            (user_id, user_id),
        ).fetchall()
        result = []
        for row in rows:
            other_id = row["user_b"] if row["user_a"] == user_id else row["user_a"]
            last = self._conn.execute(
                "SELECT body, created_at FROM guro_messages WHERE thread_id=? ORDER BY id DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            unread = self._conn.execute(
                "SELECT COUNT(*) AS n FROM guro_messages WHERE thread_id=? AND sender_id!=? AND read_at IS NULL",
                (row["id"], user_id),
            ).fetchone()["n"]
            result.append({
                "other_user_id": other_id,
                "last_message": last["body"] if last else None,
                "last_message_at": last["created_at"] if last else row["created_at"],
                "unread_count": unread,
            })
        return result

    def list_messages(self, thread_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM guro_messages WHERE thread_id=? ORDER BY id ASC", (thread_id,)
        ).fetchall()

    def mark_thread_read(self, thread_id: int, reader_id: int) -> None:
        self._conn.execute(
            "UPDATE guro_messages SET read_at=? WHERE thread_id=? AND sender_id!=? AND read_at IS NULL",
            (self._now_str(), thread_id, reader_id),
        )
        self._conn.commit()

    def count_unread_messages(self, user_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM guro_messages m JOIN guro_threads t ON m.thread_id=t.id "
            "WHERE (t.user_a=? OR t.user_b=?) AND m.sender_id!=? AND m.read_at IS NULL",
            (user_id, user_id, user_id),
        ).fetchone()
        return row["n"]

    def _count_new_threads_today(self, user_id: int) -> int:
        today_start = self._now().strftime("%Y-%m-%d 00:00:00")
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM guro_threads WHERE initiator_id=? AND created_at >= ?",
            (user_id, today_start),
        ).fetchone()
        return row["n"]

    def send_message(self, sender_id: int, recipient_id: int, body: str) -> sqlite3.Row:
        """Поднимает ValueError с кодом: SELF_MESSAGE / EMPTY_BODY /
        NO_RECIPIENT_PROFILE (бот не может написать юзеру, который никогда
        не писал боту, тот же случай, что NO_CONFIRMER_PROFILE в
        create_partnership) / SUBSCRIPTION_REQUIRED (первое сообщение
        незнакомцу без активной подписки отправителя — писать в уже
        существующий тред можно и без неё) / RATE_LIMITED (слишком много
        НОВЫХ тредов за сутки, не ограничивает переписку в открытых)."""
        if sender_id == recipient_id:
            raise ValueError("SELF_MESSAGE")
        body = body.strip()[: GC.MESSAGE_MAX_LENGTH]
        if not body:
            raise ValueError("EMPTY_BODY")
        if self.get_profile(recipient_id) is None:
            raise ValueError("NO_RECIPIENT_PROFILE")

        thread = self.find_thread(sender_id, recipient_id)
        now_str = self._now_str()
        if thread is None:
            if not self.is_subscribed(sender_id):
                raise ValueError("SUBSCRIPTION_REQUIRED")
            if self._count_new_threads_today(sender_id) >= GC.MESSAGE_MAX_NEW_THREADS_PER_DAY:
                raise ValueError("RATE_LIMITED")
            lo, hi = self._thread_pair(sender_id, recipient_id)
            cur = self._conn.execute(
                "INSERT INTO guro_threads (user_a, user_b, initiator_id, created_at, last_message_at) "
                "VALUES (?,?,?,?,?)",
                (lo, hi, sender_id, now_str, now_str),
            )
            thread_id = cur.lastrowid
        else:
            thread_id = thread["id"]

        cur = self._conn.execute(
            "INSERT INTO guro_messages (thread_id, sender_id, body, created_at) VALUES (?,?,?,?)",
            (thread_id, sender_id, body, now_str),
        )
        self._conn.execute("UPDATE guro_threads SET last_message_at=? WHERE id=?", (now_str, thread_id))
        self._conn.commit()
        return self._conn.execute("SELECT * FROM guro_messages WHERE id=?", (cur.lastrowid,)).fetchone()

    # --- статистика для /admin ------------------------------------------

    def dashboard_stats(self) -> dict:
        today_start = self._now().strftime("%Y-%m-%d 00:00:00")
        row = self._conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN status=? THEN 1 ELSE 0 END) AS confirmed, "
            "SUM(CASE WHEN status=? THEN 1 ELSE 0 END) AS pending, "
            "SUM(CASE WHEN status=? THEN 1 ELSE 0 END) AS declined, "
            "SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS created_today "
            "FROM partnerships",
            (GC.PARTNERSHIP_STATUS_CONFIRMED, GC.PARTNERSHIP_STATUS_PENDING,
             GC.PARTNERSHIP_STATUS_DECLINED, today_start),
        ).fetchone()
        rep_row = self._conn.execute(
            "SELECT AVG(reputation_score) AS avg_rep, COUNT(*) AS n FROM guro_users"
        ).fetchone()
        active_subs = self._conn.execute(
            "SELECT COUNT(*) FROM guro_users WHERE subscription_status=? AND subscription_expires_at > ?",
            (GC.SUBSCRIPTION_ACTIVE, self._now_str()),
        ).fetchone()[0]
        return {
            "total": row["total"] or 0,
            "confirmed": row["confirmed"] or 0,
            "pending": row["pending"] or 0,
            "declined": row["declined"] or 0,
            "created_today": row["created_today"] or 0,
            "tracked_users": rep_row["n"] or 0,
            "avg_reputation": rep_row["avg_rep"] or 0.0,
            "active_subscriptions": active_subs,
        }

    # --- вакансии (Фаза 4, 12.08.2026) ------------------------------------

    def create_vacancy(
        self, author_id: int, *, title: str, vertical: str | None = None, seniority: str | None = None,
        location: str | None = None, remote: bool = False, relocation: bool = False,
        salary_from: float | None = None, salary_to: float | None = None,
        salary_negotiable: bool = False, description: str | None = None, lang: str = "ru",
    ) -> sqlite3.Row:
        cur = self._conn.execute(
            "INSERT INTO guro_vacancies (author_id, title, vertical, seniority, location, remote, "
            "relocation, salary_from, salary_to, salary_negotiable, description, lang, status, "
            "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (author_id, title, vertical, seniority, location, 1 if remote else 0,
             1 if relocation else 0, salary_from, salary_to, 1 if salary_negotiable else 0,
             description, lang, GC.VACANCY_STATUS_ACTIVE, self._now_str()),
        )
        self._conn.commit()
        return self._conn.execute("SELECT * FROM guro_vacancies WHERE id=?", (cur.lastrowid,)).fetchone()

    def list_vacancies(
        self, *, lang: str | None = None, vertical: str | None = None, limit: int = GC.VACANCY_LIST_LIMIT,
    ) -> list[sqlite3.Row]:
        query = "SELECT * FROM guro_vacancies WHERE status=?"
        params: list = [GC.VACANCY_STATUS_ACTIVE]
        if lang:
            query += " AND lang=?"
            params.append(lang)
        if vertical:
            query += " AND vertical=?"
            params.append(vertical)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return self._conn.execute(query, params).fetchall()

    def list_my_vacancies(self, author_id: int) -> list[sqlite3.Row]:
        """Все свои — включая закрытые, для управления (в отличие от
        list_vacancies, которая отдаёт только активные для чужого просмотра)."""
        return self._conn.execute(
            "SELECT * FROM guro_vacancies WHERE author_id=? ORDER BY created_at DESC", (author_id,)
        ).fetchall()

    def get_vacancy(self, vacancy_id: int) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM guro_vacancies WHERE id=?", (vacancy_id,)).fetchone()

    def close_vacancy(self, vacancy_id: int, author_id: int) -> bool:
        """False — вакансии нет или закрывает не автор (проверяем тут, а не
        в API, чтобы правило жило рядом с данными)."""
        row = self.get_vacancy(vacancy_id)
        if row is None or row["author_id"] != author_id:
            return False
        self._conn.execute(
            "UPDATE guro_vacancies SET status=? WHERE id=?", (GC.VACANCY_STATUS_CLOSED, vacancy_id),
        )
        self._conn.commit()
        return True

    # --- расширение "Моё CV" (12.08.2026) ---------------------------------

    _CV_ALL_FIELDS = ("cv_profession",) + GC.CV_SIMPLE_FIELDS + (
        "cv_grade", "cv_relocation_ready", "cv_polygraph_consent",
        "cv_salary_from", "cv_salary_to", "cv_salary_negotiable",
    )

    def get_cv_extra(self, user_id: int) -> dict:
        row = self.get_or_create_guro_user(user_id)
        out = {field: row[field] for field in GC.CV_SIMPLE_FIELDS}
        out["cv_profession"] = row["cv_profession"]
        out["cv_grade"] = row["cv_grade"]
        out["cv_relocation_ready"] = None if row["cv_relocation_ready"] is None else bool(row["cv_relocation_ready"])
        out["cv_polygraph_consent"] = None if row["cv_polygraph_consent"] is None else bool(row["cv_polygraph_consent"])
        out["cv_salary_from"] = row["cv_salary_from"]
        out["cv_salary_to"] = row["cv_salary_to"]
        out["cv_salary_negotiable"] = bool(row["cv_salary_negotiable"])
        return out

    def set_cv_field(self, user_id: int, field: str, value: str | None) -> dict:
        """Простые текстовые поля CV (см. CV_SIMPLE_FIELDS) — должность и
        грейд НЕ сюда, у них своя валидация (see set_cv_profession/set_cv_grade)."""
        if field not in GC.CV_SIMPLE_FIELDS:
            raise ValueError("UNKNOWN_FIELD")
        self.get_or_create_guro_user(user_id)
        self._conn.execute(
            f"UPDATE guro_users SET {field}=?, updated_at=? WHERE user_id=?",
            (value, self._now_str(), user_id),
        )
        self._conn.commit()
        return self.get_cv_extra(user_id)

    def _count_profession_changes_last_year(self, user_id: int) -> int:
        since = self._now() - timedelta(days=365)
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM guro_profession_changes WHERE user_id=? AND changed_at>=?",
            (user_id, GL.format_db_datetime(since)),
        ).fetchone()
        return row["n"]

    def set_cv_profession(self, user_id: int, value: str) -> dict:
        """Первое заполнение пустого поля НЕ считается сменой (см. ТЗ
        владельца — лимит против "сегодня менеджер, завтра директор", не
        против заполнения анкеты с нуля). Поднимает ValueError('CHANGE_LIMIT_REACHED')."""
        row = self.get_or_create_guro_user(user_id)
        current = row["cv_profession"]
        is_real_change = bool(current) and current != value
        if is_real_change and self._count_profession_changes_last_year(user_id) >= GC.CV_PROFESSION_MAX_CHANGES_PER_YEAR:
            raise ValueError("CHANGE_LIMIT_REACHED")
        self._conn.execute(
            "UPDATE guro_users SET cv_profession=?, updated_at=? WHERE user_id=?",
            (value, self._now_str(), user_id),
        )
        if is_real_change:
            self._conn.execute(
                "INSERT INTO guro_profession_changes (user_id, changed_at) VALUES (?,?)",
                (user_id, self._now_str()),
            )
        self._conn.commit()
        return self.get_cv_extra(user_id)

    def set_cv_grade(self, user_id: int, value: str | None) -> dict:
        if value is not None and value not in GC.CV_GRADE_LEVELS:
            raise ValueError("INVALID_GRADE")
        self.get_or_create_guro_user(user_id)
        self._conn.execute(
            "UPDATE guro_users SET cv_grade=?, updated_at=? WHERE user_id=?",
            (value, self._now_str(), user_id),
        )
        self._conn.commit()
        return self.get_cv_extra(user_id)

    def set_cv_flag(self, user_id: int, field: str, value: bool | None) -> dict:
        """Тристейт (да/нет/не указано) для релокейта и полиграфа."""
        if field not in ("cv_relocation_ready", "cv_polygraph_consent"):
            raise ValueError("UNKNOWN_FIELD")
        self.get_or_create_guro_user(user_id)
        db_value = None if value is None else (1 if value else 0)
        self._conn.execute(
            f"UPDATE guro_users SET {field}=?, updated_at=? WHERE user_id=?",
            (db_value, self._now_str(), user_id),
        )
        self._conn.commit()
        return self.get_cv_extra(user_id)

    def set_cv_salary(
        self, user_id: int, *, salary_from: float | None, salary_to: float | None, negotiable: bool,
    ) -> dict:
        self.get_or_create_guro_user(user_id)
        self._conn.execute(
            "UPDATE guro_users SET cv_salary_from=?, cv_salary_to=?, cv_salary_negotiable=?, "
            "updated_at=? WHERE user_id=?",
            (salary_from, salary_to, 1 if negotiable else 0, self._now_str(), user_id),
        )
        self._conn.commit()
        return self.get_cv_extra(user_id)

    def list_cv_experience(self, user_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM guro_cv_experience WHERE user_id=? ORDER BY created_at DESC", (user_id,)
        ).fetchall()

    def add_cv_experience(
        self, user_id: int, *, company: str, position: str, date_from: str | None = None,
        date_to: str | None = None, location: str | None = None, description: str | None = None,
    ) -> sqlite3.Row:
        """Поднимает ValueError('LIMIT_REACHED') сверх CV_EXPERIENCE_MAX
        записей на человека — защита от бесконечного разрастания карточки."""
        existing = self._conn.execute(
            "SELECT COUNT(*) AS n FROM guro_cv_experience WHERE user_id=?", (user_id,)
        ).fetchone()
        if existing["n"] >= GC.CV_EXPERIENCE_MAX:
            raise ValueError("LIMIT_REACHED")
        cur = self._conn.execute(
            "INSERT INTO guro_cv_experience (user_id, company, position, date_from, date_to, "
            "location, description, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, company, position, date_from, date_to, location, description, self._now_str()),
        )
        self._conn.commit()
        return self._conn.execute("SELECT * FROM guro_cv_experience WHERE id=?", (cur.lastrowid,)).fetchone()

    def delete_cv_experience(self, entry_id: int, user_id: int) -> bool:
        row = self._conn.execute(
            "SELECT * FROM guro_cv_experience WHERE id=?", (entry_id,)
        ).fetchone()
        if row is None or row["user_id"] != user_id:
            return False
        self._conn.execute("DELETE FROM guro_cv_experience WHERE id=?", (entry_id,))
        self._conn.commit()
        return True
