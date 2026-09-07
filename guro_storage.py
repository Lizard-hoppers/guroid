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
-- 29.08.2026, аудит производительности — таблица росла без единого
-- индекса, каждый запрос (история партнёрств, ожидающие оценки, счётчики
-- по статусу/типу, дневные лимиты) был полным сканом. initiator_id/
-- confirmer_id раздельно (не составной) — под паттерн "WHERE ... AND
-- (initiator_id=? OR confirmer_id=?)", который встречается почти везде
-- (SQLite использует OR-optimization по отдельным индексам на каждой
-- стороне OR, составной индекс тут не подошёл бы). Индекс по company_id —
-- см. _init() ниже (колонка добавляется миграцией _ensure_column ПОСЛЕ
-- этой статической схемы, тут её ещё не существует).
CREATE INDEX IF NOT EXISTS idx_partnerships_initiator ON partnerships(initiator_id);
CREATE INDEX IF NOT EXISTS idx_partnerships_confirmer ON partnerships(confirmer_id);
CREATE INDEX IF NOT EXISTS idx_partnerships_status ON partnerships(status);

-- Оценки партнёрства, Шаг 2 (ТЗ 6.1, 25.08.2026) — КАЖДАЯ сторона независимо
-- оценивает КОНТРАГЕНТА (rater_id ставит оценку про ratee_id). Обе оценки
-- одного партнёрства скрыты друг от друга до раскрытия (см.
-- partnerships.rating_revealed_at) — anti-retaliation, см. ТЗ 6.1.
CREATE TABLE IF NOT EXISTS guro_partnership_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partnership_id INTEGER,
    rater_id INTEGER,
    ratee_id INTEGER,
    verdict TEXT,
    comment TEXT,
    created_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_guro_ratings_once ON guro_partnership_ratings(partnership_id, rater_id);

-- Просмотры чужих профилей подписчиками Рекрутер/Компания (ТЗ 7, 25.08.2026)
-- — рейт-лимит + эвристика скрапинга (см. guro_storage.log_profile_view).
CREATE TABLE IF NOT EXISTS guro_profile_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    viewer_id INTEGER,
    target_id INTEGER,
    viewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_guro_profile_views_viewer ON guro_profile_views(viewer_id, viewed_at);

-- Верифицированные крипто-адреса компаний (ТЗ 5.5, 25.08.2026) — ручное
-- подтверждение модератором один раз, дальше сверяются хеши (5.4).
CREATE TABLE IF NOT EXISTS guro_company_addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_user_id INTEGER,
    network TEXT,
    address TEXT,
    status TEXT DEFAULT 'pending',
    reviewed_by INTEGER,
    reviewed_at TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_guro_company_addresses_status ON guro_company_addresses(status);

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
-- 29.08.2026, аудит производительности — "Мои сообщения" (список тредов)
-- фильтрует WHERE user_a=? OR user_b=?; составной индекс выше покрывает
-- только сторону user_a (leftmost prefix), для user_b без своего индекса
-- запрос уходит в полный скан таблицы. Отдельный индекс под вторую
-- половину OR (SQLite умеет OR-optimization по отдельным индексам).
CREATE INDEX IF NOT EXISTS idx_guro_threads_user_b ON guro_threads(user_b);

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

-- Кабинет "Компания" (16.08.2026) — ТРЕТИЙ воркспейс, тот же сателлит-
-- принцип, что у кабинета рекрутера выше: не трогает guro_users/личный
-- профиль, своя ОТДЕЛЬНАЯ подписка (COMPANY_EXTRA_FIELDS +
-- PRIVACY_FIELDS-тумблеры добавляются мягкой миграцией ниже).
CREATE TABLE IF NOT EXISTS guro_company_profiles (
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

-- Отклики на вакансии — мини-ATS (ТЗ "Recruitment — ВАКАНСИИ", раздел 5,
-- 26.08.2026). Один отклик на пару (вакансия, кандидат) — уникальный
-- индекс ниже. status — воронка (см. GC.RESPONSE_STATUSES).
CREATE TABLE IF NOT EXISTS guro_vacancy_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id INTEGER,
    candidate_id INTEGER,
    status TEXT DEFAULT 'new',
    message TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_guro_vacancy_responses_pair
    ON guro_vacancy_responses(vacancy_id, candidate_id);

-- Закладки вакансий (03.09.2026, прототип владельца GURO_ID_Mini_App-2 —
-- кнопка "☆ Сохранить вакансию" на премиальной карточке). Уникальный
-- индекс на пару делает toggle идемпотентным: повторное сохранение той же
-- вакансии не может создать дубль.
CREATE TABLE IF NOT EXISTS guro_vacancy_bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    vacancy_id INTEGER,
    created_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_guro_vacancy_bookmarks_pair
    ON guro_vacancy_bookmarks(user_id, vacancy_id);
CREATE INDEX IF NOT EXISTS idx_guro_vacancy_bookmarks_user ON guro_vacancy_bookmarks(user_id);
CREATE INDEX IF NOT EXISTS idx_guro_vacancy_responses_vacancy ON guro_vacancy_responses(vacancy_id);
CREATE INDEX IF NOT EXISTS idx_guro_vacancy_responses_candidate ON guro_vacancy_responses(candidate_id);

-- Значения "Должность", введённые через "Другое" при публикации вакансии
-- (раздел 3, п.4 ТЗ) — НЕ попадают сразу в основной справочник
-- (professions_data.py), логируются тут для последующего централизованного
-- review и расширения справочника.
CREATE TABLE IF NOT EXISTS guro_vacancy_other_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id INTEGER,
    vertical TEXT,
    grade TEXT,
    text TEXT,
    created_at TEXT
);

-- "Тип компании" через "Другое" (ТЗ "Компания. каб", раздел 5, 26.08.2026) —
-- та же логика логирования нестандартных значений, что у должностей вакансий
-- выше: не сразу в основной справочник (GC.COMPANY_TYPES), для review.
CREATE TABLE IF NOT EXISTS guro_company_other_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_user_id INTEGER,
    text TEXT,
    created_at TEXT
);

-- Лимиты/конфигурация (ТЗ "Тарифы и лимиты", раздел 3, 27.08.2026) —
-- "хранить в конфигурации, не хардкодить в коде". guro_config — глобальный
-- слой (дефолт берётся из констант guro_constants.py, если строки ещё нет),
-- guro_user_limit_overrides — точечное исключение на конкретный аккаунт
-- (см. GuroStorage.get_config/get_effective_limit, handlers/admin_guro.py).
CREATE TABLE IF NOT EXISTS guro_config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS guro_user_limit_overrides (
    user_id INTEGER,
    limit_key TEXT,
    value TEXT,
    updated_at TEXT,
    PRIMARY KEY (user_id, limit_key)
);

-- Роли и команда компании (ТЗ "Роли и управление командой в кабинете
-- 'Компания'", 27.08.2026). company_id — это user_id ОСНОВАТЕЛЯ компании
-- (см. guro_company_profiles) — стабильный идентификатор компании как
-- сущности, даже после передачи владения (роли меняются, company_id — нет).
-- Человек состоит максимум в ОДНОЙ компании одновременно (проверяется на
-- уровне приложения в create_join_request/approve_join_request).
CREATE TABLE IF NOT EXISTS guro_company_members (
    company_id INTEGER,
    user_id INTEGER,
    role TEXT DEFAULT 'admin',
    position_text TEXT,
    joined_at TEXT,
    PRIMARY KEY (company_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_guro_company_members_user ON guro_company_members(user_id);

CREATE TABLE IF NOT EXISTS guro_company_join_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER,
    user_id INTEGER,
    position_text TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_guro_join_requests_company ON guro_company_join_requests(company_id, status);
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
        # 28.08.2026 (макет "09 · Приватность", Untitled-12): show_name/
        # show_company/show_vertical/show_profession ЛИЧНОГО профиля —
        # единственные из PRIVACY_FIELDS с opt-out (default=1, видно), а не
        # opt-in — макет явно показывает их включёнными по умолчанию, а не
        # скрытыми. Это касается только новых БД: у существующих строк
        # (прод) значения уже проставлены, см. migrate_privacy_opt_out_
        # default.py — одноразовая миграция, которая переводит существующих
        # пользователей на этот же opt-out (нужна, т.к. эти 4 тумблера были
        # временно вообще без гейта, см. git-историю _PRIVACY_FIELD_MAP).
        # Остальные PRIVACY_FIELDS (show_cv/show_contacts/show_offers/
        # мёртвые show_tenure/show_reputation) остаются opt-in, как были.
        _OPT_OUT_PRIVACY_FIELDS = {"show_name", "show_company", "show_vertical", "show_profession"}
        for field in GC.PRIVACY_FIELDS:
            default = 1 if field in _OPT_OUT_PRIVACY_FIELDS else 0
            self._ensure_column("guro_users", field, f"INTEGER DEFAULT {default}")
        for field in GC.EXTRA_PROFILE_FIELDS:
            self._ensure_column("guro_users", field, "TEXT")
        self._ensure_column("guro_users", "work_status", "TEXT")
        # Длина последнего оплаченного цикла подписки (28.08.2026, макет
        # "10 · Подписка") — для progress bar "осталось N дней" на фронте,
        # см. activate_subscription.
        self._ensure_column("guro_users", "subscription_cycle_days", "INTEGER")
        # 29.08.2026 — см. activate_subscription(personal_cut=...): эта
        # подписка оплачена на личный кошелёк владельца (кольцо 5:1 между
        # двумя токенами CryptoBot), исключена из dashboard_stats().
        self._ensure_column("guro_users", "subscription_personal_cut", "INTEGER DEFAULT 0")
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
        # Хэш крипто-транзакции (16.08.2026, владелец: "подкрепить реальный
        # перевод в крипте") — та же видимость, что у суммы (amount_visible),
        # отдельного тумблера не заводили, это доказательство именно суммы.
        self._ensure_column("partnerships", "tx_hash", "TEXT")
        # Один хеш = одно партнёрство (ТЗ «Hash_Uniqueness», разделы 1-2).
        # Индекс частичный по двум причинам: NULL пропускаем, потому что
        # безоплатных партнёрств без хеша может быть сколько угодно;
        # отклонённые — потому что иначе один отказ контрагента навсегда
        # сжигал бы хеш, и ту же сделку нельзя было бы переоформить
        # заново. Ожидающие подтверждения под уникальность попадают:
        # иначе десять заявок с одним хешем ушли бы одним махом.
        self._conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_partnerships_tx_hash_unique "
            "ON partnerships(tx_hash) WHERE tx_hash IS NOT NULL AND status <> 'declined'"
        )
        # Фаза 3 (12.08.2026) — витрина кабинета рекрутера, тот же набор
        # тумблеров приватности, что у личного профиля (PRIVACY_FIELDS),
        # применённый к ДРУГОЙ таблице — коллизий нет.
        for field in GC.RECRUITER_EXTRA_FIELDS:
            self._ensure_column("guro_recruiter_profiles", field, "TEXT")
        # 06.09.2026 («рекрутер каб.pdf», стр. 2) — default=1, а не 0.
        # Витрина рекрутера нужна, чтобы его находили; выключенная по
        # умолчанию, она делает оплаченный кабинет невидимым в поиске, пока
        # владелец сам не дойдёт до экрана приватности. Тот же довод, что у
        # личного профиля 28.08.2026. Существующие строки переводит
        # migrate_recruiter_privacy_default.py.
        for field in GC.PRIVACY_FIELDS:
            self._ensure_column("guro_recruiter_profiles", field, "INTEGER DEFAULT 1")
        # Главный экран кабинета "Рекрутер" (26.08.2026, ТЗ "Гуро рекрутер
        # каб"): статус активности (2.4), стаж считается от ПЕРВОЙ реальной
        # оплаты (first_activated_at), НЕ от первого open-a вкладки (тот
        # создаёт строку раньше оплаты через get_or_create, см. handle_me) —
        # проставляется один раз в activate_recruiter_subscription. Кэш
        # процентиля (2.5) — пересчитывается раз в сутки отдельным
        # скриптом (guro_recruiter_percentile_sync.py), не в реальном времени.
        self._ensure_column("guro_recruiter_profiles", "activity_status", "TEXT")
        self._ensure_column("guro_recruiter_profiles", "first_activated_at", "TEXT")
        self._ensure_column("guro_recruiter_profiles", "percentile_tier", "TEXT")
        self._ensure_column("guro_recruiter_profiles", "percentile_computed_at", "TEXT")
        # Метка кабинета-источника сообщения (2.7, "единый инбокс") — через
        # какой кабинет автор писал: 'personal'/'recruiter'/'company'.
        self._ensure_column("guro_messages", "via_workspace", "TEXT DEFAULT 'personal'")
        # Кабинет "Компания" (16.08.2026) — тот же приём, что у рекрутера
        # выше, применённый к третьей таблице.
        for field in GC.COMPANY_EXTRA_FIELDS:
            self._ensure_column("guro_company_profiles", field, "TEXT")
        # 06.09.2026 («компания.pdf», стр. 3) — default=1, как и у кабинета
        # рекрутера днём раньше: витрина нужна, чтобы компанию находили.
        # Существующие строки переводит migrate_company_privacy_default.py.
        for field in GC.PRIVACY_FIELDS:
            self._ensure_column("guro_company_profiles", field, "INTEGER DEFAULT 1")
        # Верификация (ТЗ "Компания. каб", раздел 2, 26.08.2026) — ручная,
        # бейдж включает админ (см. handlers/admin_guro.py), видимость/
        # функциональность компании НЕ зависят от статуса верификации.
        self._ensure_column("guro_company_profiles", "verified", "INTEGER DEFAULT 0")
        self._ensure_column("guro_company_profiles", "verification_requested_at", "TEXT")
        # Тир Basic/Pro (27.08.2026, ТЗ "Тарифы и лимиты") — существующие
        # подписчики компании (до этого раунда — единственный тир) считаются
        # Basic по умолчанию, пока не оплатят Pro явно.
        self._ensure_column("guro_company_profiles", "company_tier", f"TEXT DEFAULT '{GC.COMPANY_TIER_BASIC}'")
        # Роли и команда (27.08.2026, ТЗ "Роли и управление командой") —
        # кто реально нажал "Опубликовать" (для внутренней аналитики
        # компании, раздел 6 ТЗ) + чья это сделка/найм от лица компании
        # (для истории компании как единого целого, тот же раздел).
        self._ensure_column("guro_vacancies", "published_by_user_id", "INTEGER")
        self._ensure_column("partnerships", "company_id", "INTEGER")
        # 29.08.2026, аудит производительности — column добавлена этой же
        # миграцией выше, поэтому индекс на неё не может жить в статической
        # _SCHEMA (там колонки ещё нет на старой БД).
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_partnerships_company ON partnerships(company_id)")
        # Бэк-филл: КАЖДАЯ существующая компания (single-owner до этого
        # раунда) должна иметь строку "Владелец" в guro_company_members
        # СРАЗУ на старте, а не лениво при следующем заходе в /api/me — иначе
        # реальный уже оплативший владелец на секунду увидел бы "нет
        # компании" и получил бы кнопку "Создать" вместо своей существующей.
        self._conn.execute(
            "INSERT OR IGNORE INTO guro_company_members (company_id, user_id, role, joined_at) "
            "SELECT user_id, user_id, ?, COALESCE(created_at, ?) FROM guro_company_profiles",
            (GC.COMPANY_ROLE_OWNER, self._now_str()),
        )
        self._conn.commit()
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
        # Формула рейтинга v2 (25.08.2026) — total_w хранится отдельно от
        # reputation_score (кэш производного 0-100 значения, см.
        # recompute_total_w) — НЕ инкрементальный аккумулятор в 3 разных
        # местах записи (подтверждение/раскрытие оценки/синхронизация найма),
        # а всегда пересчитывается с нуля по факту БД, чтобы не рассинхронизироваться.
        self._ensure_column("guro_users", "total_w", "REAL DEFAULT 0")
        # Антискрапинг (ТЗ 7.3) — ручная заморозка/флаг подозрительной
        # активности, см. log_profile_view/freeze_account.
        self._ensure_column("guro_users", "scraping_flagged_at", "TEXT")
        self._ensure_column("guro_users", "frozen_until", "TEXT")
        # Тип сделки (ТЗ 6, п.1) — 'deal'/'hire', влияет на базовый вес (5.1).
        self._ensure_column("partnerships", "ptype", f"TEXT DEFAULT '{GC.PARTNERSHIP_TYPE_DEAL}'")
        # Порядковый номер повтора с ТЕМ ЖЕ контрагентом (5.2) и итоговый
        # базовый вес (5.1+5.2), посчитанные ОДИН раз при подтверждении
        # (Шаг 1) — используются потом при раскрытии оценки (Шаг 2) и при
        # recompute_total_w, не пересчитываются задним числом.
        self._ensure_column("partnerships", "repeat_index", "INTEGER DEFAULT 0")
        self._ensure_column("partnerships", "base_weight", "REAL DEFAULT 0")
        # Сеть верификации крипто-хеша (5.4) — ТРЕБУЕТСЯ явно от юзера при
        # заполнении tx_hash, т.к. ETH/BSC неотличимы по формату хеша.
        self._ensure_column("partnerships", "tx_network", "TEXT")
        self._ensure_column("partnerships", "tx_verified", "INTEGER DEFAULT 0")
        # Три состояния ончейн-проверки и сумма ИЗ САМОЙ транзакции (ТЗ
        # «Верификация транзакций», разделы 2-3, 06.09.2026). Старый
        # tx_verified оставлен: на нём висит расчёт рейтинга, и теперь он
        # поднимается только вместе с состоянием verified.
        self._ensure_column("partnerships", "tx_state", f"TEXT DEFAULT '{GC.TX_STATE_NONE}'")
        self._ensure_column("partnerships", "tx_amount", "REAL")
        self._ensure_column("partnerships", "tx_company_match", "INTEGER DEFAULT 0")
        self._ensure_column("partnerships", "tx_verify_error", "TEXT")
        # Анти-фрод флаг (02.09.2026, макет "06 · Сделка — шаг 1", User Flow) —
        # инициатор может пометить сделку как проблемную ещё на шаге создания
        # (до подтверждения контрагентом), независимо от вердикта "❌ Проблема"
        # на шаге 2 (rate_partnership) — тот ставится ПОСЛЕ подтверждения,
        # этот доступен сразу. Пока только сохраняется, без отдельного UI
        # для модерации — видно вручную через SQL/будущий /admin, если понадобится.
        self._ensure_column("partnerships", "is_flagged_fraud", "INTEGER DEFAULT 0")
        # "Найм" (ТЗ 6, п.3) — очки отложены, пока кандидат не сменит
        # work_status на "работаю" (см. respond_partnership/guro_partnership_sync.py).
        self._ensure_column("partnerships", "hire_status_pending", "INTEGER DEFAULT 0")
        # Раскрытие оценок Шага 2 (6.1) — оба видят обе оценки, когда обе
        # поставлены ЛИБО истёк RATING_REVEAL_TIMEOUT_DAYS с подтверждения.
        self._ensure_column("partnerships", "rating_revealed_at", "TEXT")
        # Вакансии — переработано 26.08.2026 по ТЗ "Recruitment — ВАКАНСИИ".
        # position/grade — строгий справочник (professions_data.py), title —
        # свободный текст (раздел 3.1, "два типа полей"). author_workspace —
        # 'recruiter'/'company', публикует любой из двух (раздел 1).
        self._ensure_column("guro_vacancies", "position", "TEXT")
        self._ensure_column("guro_vacancies", "position_is_other", "INTEGER DEFAULT 0")
        self._ensure_column("guro_vacancies", "grade", "TEXT")
        self._ensure_column("guro_vacancies", "work_format", "TEXT")
        self._ensure_column("guro_vacancies", "employment_type", "TEXT")
        self._ensure_column("guro_vacancies", "salary_visible", "INTEGER DEFAULT 0")
        self._ensure_column("guro_vacancies", "contact_method", f"TEXT DEFAULT '{GC.VACANCY_CONTACT_GURO_ID}'")
        self._ensure_column("guro_vacancies", "contact_url", "TEXT")
        self._ensure_column("guro_vacancies", "duration_days", f"INTEGER DEFAULT {GC.VACANCY_DURATION_DEFAULT}")
        self._ensure_column("guro_vacancies", "expires_at", "TEXT")
        self._ensure_column("guro_vacancies", "views_count", "INTEGER DEFAULT 0")
        self._ensure_column("guro_vacancies", "closed_reason", "TEXT")
        self._ensure_column("guro_vacancies", "author_workspace", "TEXT DEFAULT 'recruiter'")
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
        w = GL.tenure_bonus(created_at, self._now())
        self._conn.execute(
            "INSERT INTO guro_users (user_id, reputation_score, total_w, updated_at) VALUES (?,?,?,?)",
            (user_id, GL.reputation_from_w(w), w, self._now_str()),
        )
        self._conn.commit()
        return self._conn.execute("SELECT * FROM guro_users WHERE user_id=?", (user_id,)).fetchone()

    def any_subscription_active(self, user_id: int) -> bool:
        """6 — "личную либо через кабинет компании" — любая из трёх
        независимых подписок (личная GURO ID/рекрутер/компания) считается."""
        return (
            self.is_subscribed(user_id)
            or self.is_recruiter_subscribed(user_id)
            or self.is_company_subscribed(user_id)
        )

    def recompute_total_w(self, user_id: int) -> float:
        """Пересчитывает W С НУЛЯ по текущему состоянию БД (не инкрементальный
        аккумулятор) — включает: тенюр-бонус (5.6), базовый вес каждого
        учитываемого подтверждённого партнёрства (5.1+5.2, пропуская "найм",
        ещё не синхронизированный по статусу кандидата — см. п.3 формы), и
        поправку раскрытой оценки Шага 2 (6.1, см. GL.rating_delta) с той
        стороны, где партнёрство касается ЭТОГО user_id. Пишет
        reputation_score/total_w и возвращает новый reputation_score."""
        profile = self.get_profile(user_id)
        created_at = GL.parse_db_datetime(profile["created_at"]) if profile else None
        w = GL.tenure_bonus(created_at, self._now())

        rows = self._conn.execute(
            "SELECT * FROM partnerships WHERE status=? AND counts_toward_rating=1 "
            "AND (initiator_id=? OR confirmer_id=?)",
            (GC.PARTNERSHIP_STATUS_CONFIRMED, user_id, user_id),
        ).fetchall()
        for row in rows:
            if row["ptype"] == GC.PARTNERSHIP_TYPE_HIRE and row["hire_status_pending"]:
                continue  # 6, п.3 — найм ещё не подтверждён статусом кандидата
            base_weight = row["base_weight"] or 0.0
            w += base_weight
            if row["rating_revealed_at"]:
                other_id = row["confirmer_id"] if row["initiator_id"] == user_id else row["initiator_id"]
                rating = self._conn.execute(
                    "SELECT verdict FROM guro_partnership_ratings WHERE partnership_id=? AND rater_id=?",
                    (row["id"], other_id),
                ).fetchone()
                verdict = rating["verdict"] if rating else None
                w += GL.rating_delta(
                    verdict, base_weight,
                    tx_verified=bool(row["tx_verified"]), tx_company_match=bool(row["tx_company_match"]),
                    amount=row["amount_received"] if row["amount_received"] is not None else row["amount_paid"],
                )

        score = GL.reputation_from_w(w)
        self.get_or_create_guro_user(user_id)
        self._conn.execute(
            "UPDATE guro_users SET total_w=?, reputation_score=?, updated_at=? WHERE user_id=?",
            (w, score, self._now_str(), user_id),
        )
        self._conn.commit()
        return score

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

    def bulk_guro_users_by_id(self) -> dict[int, sqlite3.Row]:
        """29.08.2026, аудит производительности — для directory-сканов
        (guro_id_api._scan_directory_candidates), которые раньше дёргали
        get_or_create_guro_user/get_privacy/get_extra_profile/get_cv_extra
        ОТДЕЛЬНО на КАЖДОГО из list_guro_user_ids() (все они и так читают
        одну и ту же строку guro_users — 3-4 избыточных похода в БД на
        кандидата). Один SELECT * на всех, дальше словарь user_id->row в
        памяти."""
        rows = self._conn.execute("SELECT * FROM guro_users").fetchall()
        return {row["user_id"]: row for row in rows}

    def bulk_latest_profiles_by_id(self) -> dict[int, sqlite3.Row]:
        """Тот же приём, что bulk_guro_users_by_id, для profiles (см.
        get_profile — ORDER BY id DESC LIMIT 1 на пользователя; тут
        эквивалент одним запросом на всех: подзапрос берёт максимальный id
        на каждый user_id, внешний JOIN отдаёт саму строку)."""
        rows = self._conn.execute(
            "SELECT p.* FROM profiles p "
            "JOIN (SELECT user_id, MAX(id) AS max_id FROM profiles GROUP BY user_id) latest "
            "ON p.user_id = latest.user_id AND p.id = latest.max_id"
        ).fetchall()
        return {row["user_id"]: row for row in rows}

    def bulk_confirmed_partnership_counts(self) -> dict[int, int]:
        """Тот же счётчик, что count_confirmed_partnerships, но для ВСЕХ
        пользователей сразу одним проходом — не считать partnerships с нуля
        на каждого кандидата directory-скана."""
        from collections import defaultdict
        counts: dict[int, int] = defaultdict(int)
        rows = self._conn.execute(
            "SELECT initiator_id, confirmer_id FROM partnerships WHERE status=?",
            (GC.PARTNERSHIP_STATUS_CONFIRMED,),
        ).fetchall()
        for row in rows:
            for uid in {row["initiator_id"], row["confirmer_id"]}:
                counts[uid] += 1
        return dict(counts)

    def activate_subscription(self, user_id: int, duration_days: int, *, personal_cut: bool = False) -> str:
        """personal_cut (29.08.2026, владелец: "платёж на старый кошелёк —
        моя личная доля, в статистике участвовать не должна") — эта КОНКРЕТНАЯ
        оплата ушла на личный, не "бизнесовый" кошелёк владельца (см.
        guro_id_api._pick_crypto_token/handle_crypto_webhook, кольцо 5:1
        между двумя токенами CryptoBot). Подписка активируется РОВНО ТАК ЖЕ,
        как обычно — платящий получает полноценный доступ; флаг только
        исключает эту подписку из dashboard_stats().active_subscriptions
        (см. ниже). Переустанавливается на КАЖДОЙ активации (в т.ч. в False
        при обычной оплате) — статистика всегда отражает, чем оплачен
        ТЕКУЩИЙ цикл, а не унаследованное значение с прошлого."""
        row = self.get_or_create_guro_user(user_id)
        now = self._now()
        current_expires = GL.parse_db_datetime(row["subscription_expires_at"])
        is_active = GL.subscription_active(row["subscription_status"], current_expires, now)
        expires_at = GL.subscription_expires_at(
            now, duration_days, current_expires_at=current_expires if is_active else None,
        )
        # subscription_cycle_days (28.08.2026, макет "10 · Подписка") —
        # длина ПОСЛЕДНЕГО оплаченного цикла, для progress bar "осталось N
        # дней" на фронте (доля от cycle_days, не от произвольного "года").
        self._conn.execute(
            "UPDATE guro_users SET subscription_status=?, subscription_expires_at=?, "
            "subscription_cycle_days=?, subscription_personal_cut=?, updated_at=? WHERE user_id=?",
            (
                GC.SUBSCRIPTION_ACTIVE, GL.format_db_datetime(expires_at), duration_days,
                1 if personal_cut else 0, self._now_str(), user_id,
            ),
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
        row = self.get_or_create_recruiter_profile(user_id)
        now = self._now()
        current_expires = GL.parse_db_datetime(row["subscription_expires_at"])
        is_active = GL.subscription_active(row["subscription_status"], current_expires, now)
        # Тот же биллинг-баг, что и у личной подписки (28.08.2026, макет
        # "10 · Подписка"): раннее продление раньше сбрасывало остаток
        # вместо того чтобы прибавлять к нему.
        expires_at = GL.subscription_expires_at(
            now, duration_days, current_expires_at=current_expires if is_active else None,
        )
        # "Стаж в роли рекрутера" (2.3) считается от ПЕРВОЙ реальной оплаты,
        # не от первого захода на вкладку (та строку создаёт раньше, через
        # get_or_create в handle_me, ещё до оплаты) — пишем только один раз.
        first_activated_at = row["first_activated_at"] or self._now_str()
        self._conn.execute(
            "UPDATE guro_recruiter_profiles SET subscription_status=?, subscription_expires_at=?, "
            "first_activated_at=?, updated_at=? WHERE user_id=?",
            (GC.SUBSCRIPTION_ACTIVE, GL.format_db_datetime(expires_at), first_activated_at,
             self._now_str(), user_id),
        )
        self._conn.commit()
        return GL.format_db_datetime(expires_at)

    def get_recruiter_activity_status(self, user_id: int) -> str | None:
        row = self.get_or_create_recruiter_profile(user_id)
        return row["activity_status"]

    def set_recruiter_activity_status(self, user_id: int, value: str | None) -> str | None:
        """Поднимает ValueError('INVALID_STATUS') — тот же приём, что
        set_work_status личного профиля (2.4, отдельный статус от него)."""
        if value is not None and value not in GC.RECRUITER_ACTIVITY_VALUES:
            raise ValueError("INVALID_STATUS")
        self.get_or_create_recruiter_profile(user_id)
        self._conn.execute(
            "UPDATE guro_recruiter_profiles SET activity_status=?, updated_at=? WHERE user_id=?",
            (value, self._now_str(), user_id),
        )
        self._conn.commit()
        return self.get_recruiter_activity_status(user_id)

    def count_active_vacancies(self, author_id: int, workspace: str | None = None) -> int:
        """workspace (27.08.2026, ТЗ "Тарифы и лимиты", раздел 2.3) — потолок
        активных вакансий считается ОТДЕЛЬНО на каждый кабинет (Рекрутер и
        Компания — разные подписки/тарифы), не общим пулом на аккаунт.
        workspace=None (как раньше) — все воркспейсы разом, для витрин."""
        if workspace:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM guro_vacancies WHERE author_id=? AND status=? AND author_workspace=?",
                (author_id, GC.VACANCY_STATUS_ACTIVE, workspace),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM guro_vacancies WHERE author_id=? AND status=?",
                (author_id, GC.VACANCY_STATUS_ACTIVE),
            ).fetchone()
        return row["n"]

    def count_confirmed_partnerships_by_type(self, user_id: int, ptype: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM partnerships WHERE status=? AND ptype=? "
            "AND (initiator_id=? OR confirmer_id=?)",
            (GC.PARTNERSHIP_STATUS_CONFIRMED, ptype, user_id, user_id),
        ).fetchone()
        return row["n"]

    def count_confirmed_partnerships_by_type_for_company(self, company_id: int, ptype: str) -> int:
        """Панель "Характеристика" кабинета "Компания" (27.08.2026, ТЗ "экраны
        по ТЗ от 23.08") — сделки, совершённые ЛЮБЫМ участником команды "от
        лица компании" (as_company=True при подтверждении, см. handle_confirm
        partnership в guro_id_api.py), считаются на company_id как единое
        целое (раздел 6 ТЗ "Роли и команда"), а не на конкретного участника."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM partnerships WHERE status=? AND ptype=? AND company_id=?",
            (GC.PARTNERSHIP_STATUS_CONFIRMED, ptype, company_id),
        ).fetchone()
        return row["n"]

    def hire_w(self, user_id: int) -> float:
        """W_найм (ТЗ "Гуро рекрутер каб", раздел 2.5) — та же логика, что
        recompute_total_w, но ТОЛЬКО по партнёрствам ptype='hire' этого
        пользователя, и БЕЗ бонуса за стаж (это отдельная производная
        метрика для процентиля, не общий рейтинг пользователя)."""
        w = 0.0
        rows = self._conn.execute(
            "SELECT * FROM partnerships WHERE status=? AND counts_toward_rating=1 AND ptype=? "
            "AND (initiator_id=? OR confirmer_id=?)",
            (GC.PARTNERSHIP_STATUS_CONFIRMED, GC.PARTNERSHIP_TYPE_HIRE, user_id, user_id),
        ).fetchall()
        for row in rows:
            if row["hire_status_pending"]:
                continue
            base_weight = row["base_weight"] or 0.0
            w += base_weight
            if row["rating_revealed_at"]:
                other_id = row["confirmer_id"] if row["initiator_id"] == user_id else row["initiator_id"]
                rating = self._conn.execute(
                    "SELECT verdict FROM guro_partnership_ratings WHERE partnership_id=? AND rater_id=?",
                    (row["id"], other_id),
                ).fetchone()
                verdict = rating["verdict"] if rating else None
                w += GL.rating_delta(
                    verdict, base_weight,
                    tx_verified=bool(row["tx_verified"]), tx_company_match=bool(row["tx_company_match"]),
                    amount=row["amount_received"] if row["amount_received"] is not None else row["amount_paid"],
                )
        return w

    def get_recruiter_percentile(self, user_id: int) -> dict:
        """Кэш из фонового джоба (guro_recruiter_percentile_sync.py) —
        никогда не считает в реальном времени (ТЗ 2.5: "пересчёт раз в
        сутки, кешировать"). computed_at=None -> джоб ещё ни разу не
        прогонялся для этого юзера (совсем новый рекрутер) — фронт должен
        трактовать это как "недостаточно данных", как и tier=None."""
        row = self.get_or_create_recruiter_profile(user_id)
        return {"tier": row["percentile_tier"], "computed_at": row["percentile_computed_at"]}

    def set_recruiter_percentile(self, user_id: int, tier: str | None) -> None:
        self._conn.execute(
            "UPDATE guro_recruiter_profiles SET percentile_tier=?, percentile_computed_at=? WHERE user_id=?",
            (tier, self._now_str(), user_id),
        )
        self._conn.commit()

    def list_recruiter_verticals_with_hires(self) -> list[tuple[int, str]]:
        """(user_id, vertical) для ВСЕХ рекрутеров с хотя бы 1 подтверждённым
        наймом и заполненной вертикалью — вход для фонового пересчёта
        процентиля (guro_recruiter_percentile_sync.py), группировка по
        вертикали делается там."""
        rows = self._conn.execute(
            "SELECT user_id, vertical FROM guro_recruiter_profiles "
            "WHERE vertical IS NOT NULL AND vertical != ''"
        ).fetchall()
        result = []
        for row in rows:
            if self.count_confirmed_partnerships_by_type(row["user_id"], GC.PARTNERSHIP_TYPE_HIRE) > 0:
                result.append((row["user_id"], row["vertical"]))
        return result

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

    # --- кабинет "Компания" (16.08.2026) — зеркало кабинета рекрутера ---

    def get_or_create_company_profile(self, user_id: int) -> sqlite3.Row:
        """user_id тут — company_id (ОСНОВАТЕЛЬ компании, см. раздел 0 схемы
        выше). НЕ вызывать напрямую для произвольного актора — сначала
        проверить get_company_membership(user_id), иначе участник команды,
        никогда не создававший СВОЮ компанию, получит тут пустой новый
        профиль вместо компании, в которой он состоит (см. resolve_company_id
        в guro_id_api.py)."""
        row = self._conn.execute(
            "SELECT * FROM guro_company_profiles WHERE user_id=?", (user_id,)
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO guro_company_profiles (user_id, created_at, updated_at) VALUES (?,?,?)",
                (user_id, self._now_str(), self._now_str()),
            )
        # Владелец = участник команды (27.08.2026, ТЗ "Роли и команда") —
        # чинит заодно и старые компании (single-owner до этого раунда).
        self._conn.execute(
            "INSERT OR IGNORE INTO guro_company_members (company_id, user_id, role, joined_at) VALUES (?,?,?,?)",
            (user_id, user_id, GC.COMPANY_ROLE_OWNER, self._now_str()),
        )
        self._conn.commit()
        return self._conn.execute(
            "SELECT * FROM guro_company_profiles WHERE user_id=?", (user_id,)
        ).fetchone()

    # --- роли и команда (ТЗ "Роли и управление командой", 27.08.2026) ------

    def get_company_membership(self, user_id: int) -> sqlite3.Row | None:
        """Компания, в которой user_id состоит (Владелец ИЛИ Админ) — человек
        состоит максимум в одной. None — ни своей, ни чужой компании нет."""
        return self._conn.execute(
            "SELECT * FROM guro_company_members WHERE user_id=?", (user_id,)
        ).fetchone()

    def get_company_role(self, company_id: int, user_id: int) -> str | None:
        row = self._conn.execute(
            "SELECT role FROM guro_company_members WHERE company_id=? AND user_id=?", (company_id, user_id),
        ).fetchone()
        return row["role"] if row else None

    def company_member_limit(self, company_id: int) -> int:
        tier = self.get_company_tier(company_id)
        return GC.COMPANY_MEMBER_LIMIT_PRO if tier == GC.COMPANY_TIER_PRO else GC.COMPANY_MEMBER_LIMIT_BASIC

    def count_company_members(self, company_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM guro_company_members WHERE company_id=?", (company_id,),
        ).fetchone()
        return row["n"]

    def list_company_members(self, company_id: int) -> list[sqlite3.Row]:
        """Владелец первым, затем по дате вступления (раздел 3.2 ТЗ, "аватар
        + имя + должность + роль-бейдж")."""
        return self._conn.execute(
            "SELECT * FROM guro_company_members WHERE company_id=? "
            "ORDER BY (role=?) DESC, joined_at ASC",
            (company_id, GC.COMPANY_ROLE_OWNER),
        ).fetchall()

    def find_similar_companies(self, name: str, *, exclude_company_id: int | None = None) -> list[sqlite3.Row]:
        """Раздел 1.2 ТЗ — "нестрогое сравнение, с учётом похожих написаний".
        MVP: нормализация (нижний регистр, только буквы/цифры) + подстрока в
        любую сторону — без внешней библиотеки нечёткого сравнения. Не
        блокирует создание/переименование — вызывающий код показывает как
        мягкое предупреждение (см. handle_set_company_profile_field)."""
        normalized = "".join(ch for ch in name.lower() if ch.isalnum())
        if not normalized:
            return []
        rows = self._conn.execute(
            "SELECT user_id, name FROM guro_company_profiles WHERE name IS NOT NULL AND name != ''"
        ).fetchall()
        out = []
        for row in rows:
            if exclude_company_id is not None and row["user_id"] == exclude_company_id:
                continue
            candidate = "".join(ch for ch in (row["name"] or "").lower() if ch.isalnum())
            if candidate and (candidate == normalized or normalized in candidate or candidate in normalized):
                out.append(row)
        return out

    def create_join_request(self, company_id: int, user_id: int, position_text: str | None) -> sqlite3.Row:
        """Поднимает ValueError: COMPANY_NOT_FOUND / ALREADY_IN_COMPANY /
        ALREADY_REQUESTED (уже есть pending-заявка от этого же человека —
        неважно, в эту же или другую компанию, раз в компании максимум одна
        заявка/членство одновременно)."""
        company_row = self._conn.execute(
            "SELECT user_id FROM guro_company_profiles WHERE user_id=?", (company_id,),
        ).fetchone()
        if company_row is None:
            raise ValueError("COMPANY_NOT_FOUND")
        if self.get_company_membership(user_id) is not None:
            raise ValueError("ALREADY_IN_COMPANY")
        existing = self._conn.execute(
            "SELECT id FROM guro_company_join_requests WHERE user_id=? AND status=?",
            (user_id, GC.JOIN_REQUEST_PENDING),
        ).fetchone()
        if existing is not None:
            raise ValueError("ALREADY_REQUESTED")
        now_str = self._now_str()
        cur = self._conn.execute(
            "INSERT INTO guro_company_join_requests (company_id, user_id, position_text, status, created_at) "
            "VALUES (?,?,?,?,?)",
            (company_id, user_id, position_text, GC.JOIN_REQUEST_PENDING, now_str),
        )
        self._conn.commit()
        return self._conn.execute(
            "SELECT * FROM guro_company_join_requests WHERE id=?", (cur.lastrowid,),
        ).fetchone()

    def get_join_request(self, request_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM guro_company_join_requests WHERE id=?", (request_id,),
        ).fetchone()

    def list_join_requests(self, company_id: int, *, status: str = GC.JOIN_REQUEST_PENDING) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM guro_company_join_requests WHERE company_id=? AND status=? ORDER BY created_at ASC",
            (company_id, status),
        ).fetchall()

    def count_new_company_approvals_today(self, company_id: int) -> int:
        today = self._now().strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM guro_company_join_requests "
            "WHERE company_id=? AND status=? AND substr(decided_at,1,10)=?",
            (company_id, GC.JOIN_REQUEST_APPROVED, today),
        ).fetchone()
        return row["n"]

    def approve_join_request(self, request_id: int, approver_user_id: int) -> sqlite3.Row:
        """Поднимает ValueError: NOT_FOUND / NOT_OWNER / APPLICANT_ALREADY_IN_COMPANY
        (заявитель успел вступить куда-то ещё, пока заявка висела) /
        MEMBER_LIMIT_REACHED (раздел 3.4 ТЗ) / DAILY_APPROVAL_LIMIT_REACHED
        (раздел 3.5 ТЗ, не более 5/день)."""
        req = self.get_join_request(request_id)
        if req is None or req["status"] != GC.JOIN_REQUEST_PENDING:
            raise ValueError("NOT_FOUND")
        if self.get_company_role(req["company_id"], approver_user_id) != GC.COMPANY_ROLE_OWNER:
            raise ValueError("NOT_OWNER")
        if self.get_company_membership(req["user_id"]) is not None:
            raise ValueError("APPLICANT_ALREADY_IN_COMPANY")
        if self.count_company_members(req["company_id"]) >= self.company_member_limit(req["company_id"]):
            raise ValueError("MEMBER_LIMIT_REACHED")
        daily_limit = self.get_effective_limit(
            req["company_id"], GC.LIMIT_KEY_COMPANY_APPROVALS_PER_DAY, GC.LIMIT_COMPANY_APPROVALS_PER_DAY,
        )
        if self.count_new_company_approvals_today(req["company_id"]) >= daily_limit:
            raise ValueError("DAILY_APPROVAL_LIMIT_REACHED")
        now_str = self._now_str()
        self._conn.execute(
            "UPDATE guro_company_join_requests SET status=?, decided_at=? WHERE id=?",
            (GC.JOIN_REQUEST_APPROVED, now_str, request_id),
        )
        self._conn.execute(
            "INSERT INTO guro_company_members (company_id, user_id, role, position_text, joined_at) "
            "VALUES (?,?,?,?,?)",
            (req["company_id"], req["user_id"], GC.COMPANY_ROLE_ADMIN, req["position_text"], now_str),
        )
        self._conn.commit()
        return self.get_join_request(request_id)

    def reject_join_request(self, request_id: int, approver_user_id: int) -> bool:
        req = self.get_join_request(request_id)
        if req is None or req["status"] != GC.JOIN_REQUEST_PENDING:
            return False
        if self.get_company_role(req["company_id"], approver_user_id) != GC.COMPANY_ROLE_OWNER:
            return False
        self._conn.execute(
            "UPDATE guro_company_join_requests SET status=?, decided_at=? WHERE id=?",
            (GC.JOIN_REQUEST_REJECTED, self._now_str(), request_id),
        )
        self._conn.commit()
        return True

    def remove_company_member(self, company_id: int, owner_user_id: int, target_user_id: int) -> bool:
        """Раздел 4 ТЗ — прошлые сделки/вакансии участника НЕ трогаем (они
        уже физически записаны на company_id/published_by_user_id, снимок
        на момент события), просто убираем строку членства."""
        if self.get_company_role(company_id, owner_user_id) != GC.COMPANY_ROLE_OWNER:
            return False
        if target_user_id == owner_user_id:
            return False
        if self.get_company_role(company_id, target_user_id) is None:
            return False
        self._conn.execute(
            "DELETE FROM guro_company_members WHERE company_id=? AND user_id=?", (company_id, target_user_id),
        )
        self._conn.commit()
        return True

    def transfer_company_ownership(self, company_id: int, owner_user_id: int, target_user_id: int) -> bool:
        """Раздел 5 ТЗ — company_id (PK guro_company_profiles) НЕ меняется,
        меняются только роли двух строк в guro_company_members. Подписка/
        тир остаются привязаны к company_id — новый Владелец сразу может
        ей управлять, ничего мигрировать не нужно."""
        if self.get_company_role(company_id, owner_user_id) != GC.COMPANY_ROLE_OWNER:
            return False
        if target_user_id == owner_user_id:
            return False
        if self.get_company_role(company_id, target_user_id) is None:
            return False
        self._conn.execute(
            "UPDATE guro_company_members SET role=? WHERE company_id=? AND user_id=?",
            (GC.COMPANY_ROLE_ADMIN, company_id, owner_user_id),
        )
        self._conn.execute(
            "UPDATE guro_company_members SET role=? WHERE company_id=? AND user_id=?",
            (GC.COMPANY_ROLE_OWNER, company_id, target_user_id),
        )
        self._conn.commit()
        return True

    def is_company_subscribed(self, user_id: int) -> bool:
        row = self._conn.execute(
            "SELECT subscription_status, subscription_expires_at FROM guro_company_profiles WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if row is None:
            return False
        return GL.subscription_active(
            row["subscription_status"], GL.parse_db_datetime(row["subscription_expires_at"]), self._now(),
        )

    def activate_company_subscription(self, user_id: int, duration_days: int, *, tier: str = GC.COMPANY_TIER_BASIC) -> str:
        """tier (27.08.2026, ТЗ "Тарифы и лимиты") — Basic/Pro, записывается
        КАЖДЫЙ раз при активации (продление тем же тиром не меняет его,
        оплата ДРУГОГО тира — меняет; апгрейд/даунгрейд-флоу как таковой
        фронтом не предоставляется, апсейл только через новую оплату)."""
        row = self.get_or_create_company_profile(user_id)
        now = self._now()
        current_expires = GL.parse_db_datetime(row["subscription_expires_at"])
        is_active = GL.subscription_active(row["subscription_status"], current_expires, now)
        # Тот же биллинг-баг, что и у личной/рекрутерской подписки
        # (28.08.2026, макет "10 · Подписка") — раннее продление раньше
        # сбрасывало остаток вместо того чтобы прибавлять к нему. Смена
        # тира при ещё активной подписке ТОЖЕ продлевает от остатка
        # (не сбрасывает) — тот же принцип, что "продление тем же тиром"
        # выше в докстринге, апгрейд/даунгрейд не отдельный флоу.
        expires_at = GL.subscription_expires_at(
            now, duration_days, current_expires_at=current_expires if is_active else None,
        )
        self._conn.execute(
            "UPDATE guro_company_profiles SET subscription_status=?, subscription_expires_at=?, "
            "company_tier=?, updated_at=? WHERE user_id=?",
            (GC.SUBSCRIPTION_ACTIVE, GL.format_db_datetime(expires_at), tier, self._now_str(), user_id),
        )
        self._conn.commit()
        return GL.format_db_datetime(expires_at)

    def get_company_tier(self, user_id: int) -> str:
        row = self._conn.execute(
            "SELECT company_tier FROM guro_company_profiles WHERE user_id=?", (user_id,),
        ).fetchone()
        return (row["company_tier"] if row and row["company_tier"] else GC.COMPANY_TIER_BASIC)

    def get_company_extra(self, user_id: int) -> dict:
        row = self.get_or_create_company_profile(user_id)
        return {field: row[field] for field in GC.COMPANY_EXTRA_FIELDS}

    def set_company_extra_field(self, user_id: int, field: str, value: str | None) -> dict:
        if field not in GC.COMPANY_EXTRA_FIELDS:
            raise ValueError("UNKNOWN_FIELD")
        self.get_or_create_company_profile(user_id)
        self._conn.execute(
            f"UPDATE guro_company_profiles SET {field}=?, updated_at=? WHERE user_id=?",
            (value, self._now_str(), user_id),
        )
        self._conn.commit()
        return self.get_company_extra(user_id)

    def get_company_privacy(self, user_id: int) -> dict:
        row = self.get_or_create_company_profile(user_id)
        return {field: bool(row[field]) for field in GC.PRIVACY_FIELDS}

    def set_company_privacy_field(self, user_id: int, field: str, value: bool) -> dict:
        if field not in GC.PRIVACY_FIELDS:
            raise ValueError("UNKNOWN_FIELD")
        self.get_or_create_company_profile(user_id)
        self._conn.execute(
            f"UPDATE guro_company_profiles SET {field}=?, updated_at=? WHERE user_id=?",
            (1 if value else 0, self._now_str(), user_id),
        )
        self._conn.commit()
        return self.get_company_privacy(user_id)

    # --- верификация компании (ТЗ "Компания. каб", раздел 2, 26.08.2026) -----
    # Ручная, MVP: владелец шлёт письмо с доменной почты администратору,
    # тот вручную сверяет и переключает бейдж тут. Компания видна и полностью
    # функциональна независимо от статуса — бейдж лишь визуальная отметка.

    def is_company_verified(self, user_id: int) -> bool:
        row = self._conn.execute(
            "SELECT verified FROM guro_company_profiles WHERE user_id=?", (user_id,),
        ).fetchone()
        return bool(row["verified"]) if row else False

    def request_company_verification(self, user_id: int) -> None:
        self.get_or_create_company_profile(user_id)
        self._conn.execute(
            "UPDATE guro_company_profiles SET verification_requested_at=? WHERE user_id=?",
            (self._now_str(), user_id),
        )
        self._conn.commit()

    def set_company_verified(self, user_id: int, verified: bool) -> bool:
        """Ручное переключение админом (handlers/admin_guro.py). Возвращает
        False, если у такого user_id ещё нет строки кабинета компании."""
        row = self._conn.execute(
            "SELECT user_id FROM guro_company_profiles WHERE user_id=?", (user_id,),
        ).fetchone()
        if row is None:
            return False
        self._conn.execute(
            "UPDATE guro_company_profiles SET verified=?, updated_at=? WHERE user_id=?",
            (1 if verified else 0, self._now_str(), user_id),
        )
        self._conn.commit()
        return True

    def list_companies_for_verification(self) -> list[sqlite3.Row]:
        """Для админ-экрана "Компании на верификацию" — только те, у кого
        реально есть смысл смотреть: активная подписка или уже была подана
        заявка (иначе список захламляется пустыми созданными-по-факту-захода
        строками, см. get_or_create_company_profile)."""
        now_str = self._now_str()
        return self._conn.execute(
            "SELECT * FROM guro_company_profiles WHERE verification_requested_at IS NOT NULL "
            "OR (subscription_status=? AND subscription_expires_at > ?) "
            "ORDER BY verified ASC, verification_requested_at DESC",
            (GC.SUBSCRIPTION_ACTIVE, now_str),
        ).fetchall()

    def log_company_other_type(self, user_id: int, text: str) -> None:
        """"Другое" в поле "Тип компании" (раздел 5 ТЗ) — та же логика, что
        у нестандартных должностей вакансий: не сразу в справочник, копится
        для последующего централизованного review."""
        self._conn.execute(
            "INSERT INTO guro_company_other_types (company_user_id, text, created_at) VALUES (?,?,?)",
            (user_id, text, self._now_str()),
        )
        self._conn.commit()

    # --- лимиты/конфигурация (ТЗ "Тарифы и лимиты", раздел 3, 27.08.2026) ----

    def get_config(self, key: str, default: int) -> int:
        row = self._conn.execute("SELECT value FROM guro_config WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            return default

    def set_config(self, key: str, value: int) -> None:
        self._conn.execute(
            "INSERT INTO guro_config (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, str(value), self._now_str()),
        )
        self._conn.commit()

    def get_user_limit_override(self, user_id: int, key: str) -> int | None:
        row = self._conn.execute(
            "SELECT value FROM guro_user_limit_overrides WHERE user_id=? AND limit_key=?", (user_id, key),
        ).fetchone()
        if row is None:
            return None
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            return None

    def set_user_limit_override(self, user_id: int, key: str, value: int) -> None:
        self._conn.execute(
            "INSERT INTO guro_user_limit_overrides (user_id, limit_key, value, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id, limit_key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (user_id, key, str(value), self._now_str()),
        )
        self._conn.commit()

    def clear_user_limit_override(self, user_id: int, key: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM guro_user_limit_overrides WHERE user_id=? AND limit_key=?", (user_id, key),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_user_limit_overrides(self, user_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM guro_user_limit_overrides WHERE user_id=? ORDER BY limit_key", (user_id,),
        ).fetchall()

    def get_effective_limit(self, user_id: int, key: str, default: int) -> int:
        """Оверрайд на аккаунт (если есть) -> глобальный конфиг (если есть)
        -> дефолт-константа. Один и тот же key используется в обеих
        таблицах — так проще, чем городить отдельные схемы ключей."""
        override = self.get_user_limit_override(user_id, key)
        if override is not None:
            return override
        return self.get_config(key, default)

    def count_new_partnerships_today(self, initiator_id: int) -> int:
        """2.2 ТЗ — НОВЫЕ заявки на партнёрство/найм за сегодня (UTC), не
        путать с count_confirmed_partnerships_by_type (уже подтверждённые —
        не лимитируются, ограничивать реальный бизнес нельзя)."""
        today = self._now().strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM partnerships WHERE initiator_id=? AND company_id IS NULL "
            "AND substr(created_at,1,10)=?",
            (initiator_id, today),
        ).fetchone()
        return row["n"]

    def count_new_company_partnerships_today(self, company_id: int) -> int:
        """Тот же лимит (2.2 ТЗ "Тарифы и лимиты"), но "на аккаунт компании
        в целом" (раздел 2.2, "не на участника") — считается по company_id,
        общий на всю команду, независимо от того, кто из участников вёл
        сделку (см. as_company в handle_create_partnership)."""
        today = self._now().strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM partnerships WHERE company_id=? AND substr(created_at,1,10)=?",
            (company_id, today),
        ).fetchone()
        return row["n"]

    def count_new_vacancies_today(self, author_id: int) -> int:
        """2.3 ТЗ — дневной лимит НОВЫХ публикаций (общий на автора, вне
        зависимости от воркспейса — публикация вакансии одна и та же
        механика что от Рекрутера, что от Компании)."""
        today = self._now().strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM guro_vacancies WHERE author_id=? AND substr(created_at,1,10)=?",
            (author_id, today),
        ).fetchone()
        return row["n"]

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
        tx_hash: str | None = None, ptype: str = GC.PARTNERSHIP_TYPE_DEAL,
        tx_network: str | None = None, tx_verified: bool = False, tx_company_match: bool = False,
        tx_state: str = GC.TX_STATE_NONE, tx_amount: float | None = None,
        tx_verify_error: str | None = None, company_id: int | None = None,
        is_flagged_fraud: bool = False,
    ) -> sqlite3.Row:
        """Поднимает ValueError с понятным кодом-строкой при нарушении правил
        (see ТЗ п.4/п.8): NO_CONFIRMER_PROFILE / SELF_PARTNERSHIP / RATE_LIMITED /
        INVALID_TYPE. company_id (27.08.2026, ТЗ "Роли и команда", раздел 6) —
        если инициатор действовал "от лица компании", сделка попадает в
        историю КОМПАНИИ как единое целое; initiator_id остаётся конкретным
        человеком команды, который её вёл ("какой участник это сделал").
        offer/amount_*/review/amount_visible (Фаза 2, 11.08.2026) —
        заполняет ТОЛЬКО инициатор в момент создания заявки; confirmer лишь
        подтверждает/отклоняет кнопкой, отдельной формы у него нет (см. план).
        ptype/tx_* (25.08.2026, ТЗ "формула рейтинга") — тип сделки и
        результат ончейн-верификации хеша (уже посчитан ВЫЗЫВАЮЩИМ кодом,
        guro_id_api.handle_create_partnership, т.к. это async-сеть, а
        storage синхронный). Итоговый вес (base_weight)/repeat_index/
        counts_toward_rating считаются НЕ здесь, а в respond_partnership —
        на момент ПОДТВЕРЖДЕНИЯ (стаж/подписка проверяются live, могли
        измениться между заявкой и ответом)."""
        if ptype not in GC.PARTNERSHIP_TYPES:
            raise ValueError("INVALID_TYPE")
        if initiator_id == confirmer_id:
            raise ValueError("SELF_PARTNERSHIP")
        confirmer_profile = self.get_profile(confirmer_id)
        if confirmer_profile is None:
            # Bot API не может написать юзеру, который никогда не писал боту.
            raise ValueError("NO_CONFIRMER_PROFILE")

        now = self._now()
        if GL.rate_limited(self._last_request_between(initiator_id, confirmer_id), now):
            raise ValueError("RATE_LIMITED")

        cur = self._conn.execute(
            "INSERT INTO partnerships (initiator_id, confirmer_id, status, vertical, geo, "
            "counts_toward_rating, created_at, offer, amount_received, amount_paid, review, "
            "amount_visible, tx_hash, ptype, tx_network, tx_verified, tx_company_match, "
            "tx_verify_error, company_id, is_flagged_fraud, tx_state, tx_amount) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (initiator_id, confirmer_id, GC.PARTNERSHIP_STATUS_PENDING, vertical, geo,
             0, GL.format_db_datetime(now), offer, amount_received, amount_paid,
             review, 1 if amount_visible else 0, tx_hash, ptype, tx_network,
             1 if tx_verified else 0, 1 if tx_company_match else 0, tx_verify_error, company_id,
             1 if is_flagged_fraud else 0, tx_state, tx_amount),
        )
        self._conn.commit()
        return self._conn.execute("SELECT * FROM partnerships WHERE id=?", (cur.lastrowid,)).fetchone()

    def find_partnership_by_tx_hash(self, tx_hash: str) -> sqlite3.Row | None:
        """Партнёрство, уже занявшее этот хеш (ТЗ «Hash_Uniqueness»,
        раздел 2). Отклонённые не в счёт — см. комментарий у индекса."""
        return self._conn.execute(
            "SELECT * FROM partnerships WHERE tx_hash = ? AND status <> ? LIMIT 1",
            (tx_hash, GC.PARTNERSHIP_STATUS_DECLINED),
        ).fetchone()

    def turnover_stats(self, user_id: int) -> dict:
        """Счётчики оборота (ТЗ «Верификация транзакций», разделы 7-8).

        Считаются только ПОДТВЕРЖДЁННЫЕ партнёрства и только там, где
        инициатор включил показ суммы. В «подтверждённый» оборот идут лишь
        сделки со состоянием verified — то есть с реальной транзакцией в
        блокчейне, сумма которой сошлась с заявленной. Остальное копится
        отдельно и показывается приглушённо.

        Суммы вводит инициатор от себя, поэтому для второй стороны они
        зеркалятся: полученное инициатором = оплаченное контрагентом.
        """
        row = self._conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN tx_state = ? THEN
                CASE WHEN initiator_id = ? THEN COALESCE(amount_received, 0)
                     ELSE COALESCE(amount_paid, 0) END END), 0) AS verified_received,
              COALESCE(SUM(CASE WHEN tx_state = ? THEN
                CASE WHEN initiator_id = ? THEN COALESCE(amount_paid, 0)
                     ELSE COALESCE(amount_received, 0) END END), 0) AS verified_paid,
              COALESCE(SUM(CASE WHEN tx_state IS NULL OR tx_state <> ? THEN
                CASE WHEN initiator_id = ? THEN COALESCE(amount_received, 0)
                     ELSE COALESCE(amount_paid, 0) END END), 0) AS unverified_received,
              COALESCE(SUM(CASE WHEN tx_state IS NULL OR tx_state <> ? THEN
                CASE WHEN initiator_id = ? THEN COALESCE(amount_paid, 0)
                     ELSE COALESCE(amount_received, 0) END END), 0) AS unverified_paid
            FROM partnerships
            WHERE status = ? AND amount_visible = 1
              AND (initiator_id = ? OR confirmer_id = ?)
            """,
            (GC.TX_STATE_VERIFIED, user_id, GC.TX_STATE_VERIFIED, user_id,
             GC.TX_STATE_VERIFIED, user_id, GC.TX_STATE_VERIFIED, user_id,
             GC.PARTNERSHIP_STATUS_CONFIRMED, user_id, user_id),
        ).fetchone()
        return {
            "received": round(row["verified_received"], 2),
            "paid": round(row["verified_paid"], 2),
            "unverified_received": round(row["unverified_received"], 2),
            "unverified_paid": round(row["unverified_paid"], 2),
        }

    def get_partnership(self, partnership_id: int) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM partnerships WHERE id=?", (partnership_id,)).fetchone()

    def list_company_partnerships(self, company_id: int, *, limit: int = 100) -> list[sqlite3.Row]:
        """Раздел 6 ТЗ "Роли и команда" — история компании как единое целое,
        независимо от того, какой конкретно участник вёл каждую сделку."""
        return self._conn.execute(
            "SELECT * FROM partnerships WHERE company_id=? ORDER BY created_at DESC LIMIT ?",
            (company_id, limit),
        ).fetchall()

    def _confirmed_count_between(self, user_a: int, user_b: int) -> int:
        """5.2 — сколько раз этот же контрагент УЖЕ был подтверждён ДО этого
        момента (независимо от того, кто из пары инициировал)."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM partnerships WHERE status=? AND "
            "((initiator_id=? AND confirmer_id=?) OR (initiator_id=? AND confirmer_id=?))",
            (GC.PARTNERSHIP_STATUS_CONFIRMED, user_a, user_b, user_b, user_a),
        ).fetchone()
        return row["n"]

    def respond_partnership(self, partnership_id: int, responder_id: int, accept: bool) -> sqlite3.Row:
        """Поднимает ValueError: NOT_FOUND / NOT_YOUR_REQUEST / ALREADY_RESOLVED.

        При accept=True (25.08.2026, ТЗ "формула рейтинга") — считает
        counts_toward_rating НА МОМЕНТ ПОДТВЕРЖДЕНИЯ (не на момент заявки,
        см. create_partnership): стаж ОБОИХ (как раньше) И "оба участника
        должны иметь активную подписку" (6, новое условие) — любую из
        трёх (личную/рекрутер/компания). Для типа "Найм" (6, п.3) —
        дополнительно требуется, чтобы ХОТЯ БЫ ОДИН из пары (кандидат,
        роль не уточняется в ТЗ) имел work_status="working"; если нет —
        партнёрство всё равно подтверждается и видимо, но очки откладываются
        (hire_status_pending=1) до guro_partnership_sync.py."""
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
        initiator_id, confirmer_id = row["initiator_id"], row["confirmer_id"]
        initiator_profile = self.get_profile(initiator_id)
        confirmer_profile = self.get_profile(confirmer_id)
        tenure_ok = GL.counts_toward_rating(
            GL.parse_db_datetime(initiator_profile["created_at"]) if initiator_profile else None,
            GL.parse_db_datetime(confirmer_profile["created_at"]) if confirmer_profile else None,
            now,
        )
        subscription_ok = self.any_subscription_active(initiator_id) and self.any_subscription_active(confirmer_id)
        counts = tenure_ok and subscription_ok

        repeat_index = self._confirmed_count_between(initiator_id, confirmer_id) if counts else 0
        base_weight = GL.partnership_base_weight(row["ptype"], repeat_index) if counts else 0.0

        hire_pending = 0
        if counts and row["ptype"] == GC.PARTNERSHIP_TYPE_HIRE:
            candidate_working = (
                self.get_work_status(initiator_id) == GC.WORK_STATUS_WORKING
                or self.get_work_status(confirmer_id) == GC.WORK_STATUS_WORKING
            )
            hire_pending = 0 if candidate_working else 1

        self._conn.execute(
            "UPDATE partnerships SET status=?, confirmed_at=?, counts_toward_rating=?, "
            "repeat_index=?, base_weight=?, hire_status_pending=? WHERE id=?",
            (GC.PARTNERSHIP_STATUS_CONFIRMED, GL.format_db_datetime(now), 1 if counts else 0,
             repeat_index, base_weight, hire_pending, partnership_id),
        )
        self._conn.commit()
        self.recompute_total_w(initiator_id)
        self.recompute_total_w(confirmer_id)
        return self.get_partnership(partnership_id)

    # --- оценка партнёрства, Шаг 2 (ТЗ 6.1, 25.08.2026) --------------------

    def submit_rating(self, partnership_id: int, rater_id: int, verdict: str, comment: str | None) -> sqlite3.Row:
        """Поднимает ValueError: NOT_FOUND / NOT_YOUR_PARTNERSHIP /
        NOT_CONFIRMED / INVALID_VERDICT. Комментарий разрешён только у
        "problematic" (см. ТЗ 6.1) — для остальных обнуляется молча, не 400
        (не критично для юзера).

        25.08.2026 (фидбек владельца, "Правки.pdf"): раньше повторная
        оценка от той же стороны кидала ALREADY_RATED — теперь UPSERT
        ("добавить возможность редактирования"), можно менять вердикт
        сколько угодно раз. Если партнёрство уже РАСКРЫТО
        (rating_revealed_at) — пересчитываем W контрагента сразу же (см.
        delete_rating — тот же приём), иначе прежнее поведение (эффект
        применится при раскрытии) не меняется."""
        if verdict not in GC.RATING_VERDICTS:
            raise ValueError("INVALID_VERDICT")
        row = self.get_partnership(partnership_id)
        if row is None:
            raise ValueError("NOT_FOUND")
        if rater_id not in (row["initiator_id"], row["confirmer_id"]):
            raise ValueError("NOT_YOUR_PARTNERSHIP")
        if row["status"] != GC.PARTNERSHIP_STATUS_CONFIRMED:
            raise ValueError("NOT_CONFIRMED")
        ratee_id = row["confirmer_id"] if rater_id == row["initiator_id"] else row["initiator_id"]

        # 28.08.2026 (макет "07 · Сделки — шаг 2", Untitled-10): раньше
        # комментарий сохранялся ТОЛЬКО у "problematic", для "nuance" молча
        # обнулялся, даже если фронт его прислал — макет явно требует
        # комментарий для ОБОИХ негативных вердиктов ("Комментарий обязателен
        # при ⚠ «Были нюансы» или ❌ «Проблемная сделка»"). Теперь "success" —
        # единственный вердикт, где комментарий необязателен и отбрасывается.
        comment = (comment or "").strip()[: GC.RATING_COMMENT_MAX] or None
        if verdict == GC.RATING_SUCCESS:
            comment = None
        elif comment is None:
            raise ValueError("COMMENT_REQUIRED")
        existing = self._conn.execute(
            "SELECT id FROM guro_partnership_ratings WHERE partnership_id=? AND rater_id=?",
            (partnership_id, rater_id),
        ).fetchone()
        if existing is not None:
            self._conn.execute(
                "UPDATE guro_partnership_ratings SET verdict=?, comment=?, created_at=? WHERE id=?",
                (verdict, comment, self._now_str(), existing["id"]),
            )
        else:
            self._conn.execute(
                "INSERT INTO guro_partnership_ratings (partnership_id, rater_id, ratee_id, verdict, "
                "comment, created_at) VALUES (?,?,?,?,?,?)",
                (partnership_id, rater_id, ratee_id, verdict, comment, self._now_str()),
            )
        self._conn.commit()
        if row["rating_revealed_at"]:
            self.recompute_total_w(ratee_id)
        else:
            self._maybe_reveal_rating(partnership_id)
        return self.get_partnership(partnership_id)

    def delete_rating(self, partnership_id: int, rater_id: int) -> None:
        """Удаление своей оценки (25.08.2026, фидбек владельца: "удалить
        может тот, кто отзыв оставил"). Поднимает ValueError: NOT_FOUND /
        NOT_YOUR_PARTNERSHIP / RATING_NOT_FOUND. Если партнёрство уже
        раскрыто — сразу пересчитываем W контрагента (эффект этой оценки
        исчезает, rating_delta(None,...) = нейтрально, см. guro_logic)."""
        row = self.get_partnership(partnership_id)
        if row is None:
            raise ValueError("NOT_FOUND")
        if rater_id not in (row["initiator_id"], row["confirmer_id"]):
            raise ValueError("NOT_YOUR_PARTNERSHIP")
        ratee_id = row["confirmer_id"] if rater_id == row["initiator_id"] else row["initiator_id"]

        existing = self._conn.execute(
            "SELECT id FROM guro_partnership_ratings WHERE partnership_id=? AND rater_id=?",
            (partnership_id, rater_id),
        ).fetchone()
        if existing is None:
            raise ValueError("RATING_NOT_FOUND")
        self._conn.execute("DELETE FROM guro_partnership_ratings WHERE id=?", (existing["id"],))
        self._conn.commit()
        if row["rating_revealed_at"]:
            self.recompute_total_w(ratee_id)

    def get_my_rating(self, partnership_id: int, user_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM guro_partnership_ratings WHERE partnership_id=? AND rater_id=?",
            (partnership_id, user_id),
        ).fetchone()

    def get_rating_of(self, partnership_id: int, ratee_id: int) -> sqlite3.Row | None:
        """Оценка КОНТРАГЕНТОМ этого user_id — видна вызывающему коду только
        если partnerships.rating_revealed_at уже проставлен (проверяется на
        уровне API, см. guro_id_api._profile_summary)."""
        return self._conn.execute(
            "SELECT * FROM guro_partnership_ratings WHERE partnership_id=? AND ratee_id=?",
            (partnership_id, ratee_id),
        ).fetchone()

    def _maybe_reveal_rating(self, partnership_id: int) -> None:
        """Раскрывает обе оценки, если ОБЕ уже поставлены — anti-retaliation
        таймаут (истечение RATING_REVEAL_TIMEOUT_DAYS) обрабатывает отдельно
        guro_partnership_sync.py (тут — только "обе сразу")."""
        row = self.get_partnership(partnership_id)
        if row is None or row["rating_revealed_at"]:
            return
        count = self._conn.execute(
            "SELECT COUNT(*) AS n FROM guro_partnership_ratings WHERE partnership_id=?",
            (partnership_id,),
        ).fetchone()["n"]
        if count < 2:
            return
        self._reveal_rating(partnership_id)

    def _reveal_rating(self, partnership_id: int) -> None:
        row = self.get_partnership(partnership_id)
        if row is None or row["rating_revealed_at"]:
            return
        self._conn.execute(
            "UPDATE partnerships SET rating_revealed_at=? WHERE id=?",
            (self._now_str(), partnership_id),
        )
        self._conn.commit()
        self.recompute_total_w(row["initiator_id"])
        self.recompute_total_w(row["confirmer_id"])

    def list_partnerships_awaiting_reveal(self) -> list[sqlite3.Row]:
        """Для guro_partnership_sync.py (таймаут раскрытия) — подтверждённые,
        ещё не раскрытые, старше RATING_REVEAL_TIMEOUT_DAYS с подтверждения."""
        cutoff = self._now() - timedelta(days=GC.RATING_REVEAL_TIMEOUT_DAYS)
        return self._conn.execute(
            "SELECT * FROM partnerships WHERE status=? AND rating_revealed_at IS NULL "
            "AND confirmed_at IS NOT NULL AND confirmed_at<=?",
            (GC.PARTNERSHIP_STATUS_CONFIRMED, GL.format_db_datetime(cutoff)),
        ).fetchall()

    def reveal_rating_by_timeout(self, partnership_id: int) -> None:
        self._reveal_rating(partnership_id)

    def list_hire_pending_partnerships(self) -> list[sqlite3.Row]:
        """Для guro_partnership_sync.py — "найм" в ожидании синка статуса
        кандидата (6, п.3)."""
        return self._conn.execute(
            "SELECT * FROM partnerships WHERE status=? AND ptype=? AND hire_status_pending=1",
            (GC.PARTNERSHIP_STATUS_CONFIRMED, GC.PARTNERSHIP_TYPE_HIRE),
        ).fetchall()

    def sync_hire_status(self, partnership_id: int) -> bool:
        """True, если кандидат теперь working и очки применены (снимает
        hire_status_pending + пересчитывает W обеих сторон)."""
        row = self.get_partnership(partnership_id)
        if row is None or not row["hire_status_pending"]:
            return False
        candidate_working = (
            self.get_work_status(row["initiator_id"]) == GC.WORK_STATUS_WORKING
            or self.get_work_status(row["confirmer_id"]) == GC.WORK_STATUS_WORKING
        )
        if not candidate_working:
            return False
        self._conn.execute(
            "UPDATE partnerships SET hire_status_pending=0 WHERE id=?", (partnership_id,),
        )
        self._conn.commit()
        self.recompute_total_w(row["initiator_id"])
        self.recompute_total_w(row["confirmer_id"])
        return True

    # --- антифрод поиска/просмотра профилей (ТЗ 7, 25.08.2026) ------------
    # Применяется ТОЛЬКО к просмотрам подписчиков Рекрутер/Компания (см.
    # guro_id_api._check_profile_view) — обычные пользователи не лимитируются.

    def is_frozen(self, user_id: int) -> bool:
        row = self._conn.execute(
            "SELECT frozen_until FROM guro_users WHERE user_id=?", (user_id,)
        ).fetchone()
        if row is None or row["frozen_until"] is None:
            return False
        expires = GL.parse_db_datetime(row["frozen_until"])
        return expires is not None and expires > self._now()

    def freeze_account(self, user_id: int, hours: int = GC.ACCOUNT_FREEZE_HOURS) -> str:
        self.get_or_create_guro_user(user_id)
        until = self._now() + timedelta(hours=hours)
        self._conn.execute(
            "UPDATE guro_users SET frozen_until=?, updated_at=? WHERE user_id=?",
            (GL.format_db_datetime(until), self._now_str(), user_id),
        )
        self._conn.commit()
        return GL.format_db_datetime(until)

    def unfreeze_account(self, user_id: int) -> None:
        self._conn.execute(
            "UPDATE guro_users SET frozen_until=NULL, scraping_flagged_at=NULL, updated_at=? WHERE user_id=?",
            (self._now_str(), user_id),
        )
        self._conn.commit()

    def _profile_views_since(self, viewer_id: int, since: datetime) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM guro_profile_views WHERE viewer_id=? AND viewed_at>=?",
            (viewer_id, GL.format_db_datetime(since)),
        ).fetchone()
        return row["n"]

    def profile_views_today(self, viewer_id: int) -> int:
        today_start = self._now().strftime("%Y-%m-%d 00:00:00")
        return self._profile_views_since(viewer_id, GL.parse_db_datetime(today_start) or self._now())

    def log_profile_view(self, viewer_id: int, target_id: int) -> None:
        """Пишет просмотр И флагает аккаунт на ручную проверку (7.3), если
        поймали "всплеск" (SCRAPING_BURST_COUNT просмотров за
        SCRAPING_BURST_MINUTES минут) — флаг НЕ блокирует, только помечает
        для /admin (заморозка — отдельное ручное действие, freeze_account)."""
        now = self._now()
        self._conn.execute(
            "INSERT INTO guro_profile_views (viewer_id, target_id, viewed_at) VALUES (?,?,?)",
            (viewer_id, target_id, GL.format_db_datetime(now)),
        )
        self._conn.commit()
        burst_since = now - timedelta(minutes=GC.SCRAPING_BURST_MINUTES)
        if self._profile_views_since(viewer_id, burst_since) >= GC.SCRAPING_BURST_COUNT:
            self.get_or_create_guro_user(viewer_id)
            self._conn.execute(
                "UPDATE guro_users SET scraping_flagged_at=? WHERE user_id=? AND scraping_flagged_at IS NULL",
                (self._now_str(), viewer_id),
            )
            self._conn.commit()

    def list_flagged_accounts(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM guro_users WHERE scraping_flagged_at IS NOT NULL ORDER BY scraping_flagged_at DESC"
        ).fetchall()

    # --- верификация адреса компании (ТЗ 5.5, 25.08.2026) -----------------

    def submit_company_address(self, company_user_id: int, network: str, address: str) -> sqlite3.Row:
        if network not in GC.TX_NETWORKS:
            raise ValueError("INVALID_NETWORK")
        address = address.strip()
        if not address:
            raise ValueError("EMPTY_ADDRESS")
        cur = self._conn.execute(
            "INSERT INTO guro_company_addresses (company_user_id, network, address, status, created_at) "
            "VALUES (?,?,?,?,?)",
            (company_user_id, network, address, "pending", self._now_str()),
        )
        self._conn.commit()
        return self._conn.execute(
            "SELECT * FROM guro_company_addresses WHERE id=?", (cur.lastrowid,)
        ).fetchone()

    def list_company_addresses(self, company_user_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM guro_company_addresses WHERE company_user_id=? ORDER BY created_at DESC",
            (company_user_id,),
        ).fetchall()

    def list_pending_company_addresses(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM guro_company_addresses WHERE status='pending' ORDER BY created_at ASC"
        ).fetchall()

    def review_company_address(self, address_id: int, reviewer_id: int, approve: bool) -> bool:
        row = self._conn.execute(
            "SELECT * FROM guro_company_addresses WHERE id=?", (address_id,)
        ).fetchone()
        if row is None or row["status"] != "pending":
            return False
        self._conn.execute(
            "UPDATE guro_company_addresses SET status=?, reviewed_by=?, reviewed_at=? WHERE id=?",
            ("approved" if approve else "rejected", reviewer_id, self._now_str(), address_id),
        )
        self._conn.commit()
        return True

    def verified_company_addresses(self) -> set[tuple[str, str]]:
        """Множество (network, address_lowercase) верифицированных адресов
        компаний — для сверки при верификации хеша (5.4/5.5), см.
        guro_chain_verify.matches_company_address."""
        rows = self._conn.execute(
            "SELECT network, address FROM guro_company_addresses WHERE status='approved'"
        ).fetchall()
        return {(r["network"], r["address"].lower()) for r in rows}

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

    def send_message(
        self, sender_id: int, recipient_id: int, body: str, *, via_workspace: str = "personal",
    ) -> sqlite3.Row:
        """Поднимает ValueError с кодом: SELF_MESSAGE / EMPTY_BODY /
        NO_RECIPIENT_PROFILE (бот не может написать юзеру, который никогда
        не писал боту, тот же случай, что NO_CONFIRMER_PROFILE в
        create_partnership) / SUBSCRIPTION_REQUIRED (первое сообщение
        незнакомцу без ЛЮБОЙ активной подписки отправителя — личной,
        рекрутера или компании, см. any_subscription_active; писать в уже
        существующий тред можно и без неё) / RATE_LIMITED (слишком много
        НОВЫХ тредов за сутки, не ограничивает переписку в открытых).
        via_workspace (26.08.2026, ТЗ "Гуро рекрутер каб" 2.7, "единый
        инбокс") — метка, через какой кабинет отправитель писал это
        сообщение, для показа собеседнику ("Написал через Кабинет:
        Рекрутер") — сам инбокс общий, это только ярлык на записи."""
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
            if not self.any_subscription_active(sender_id):
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
            "INSERT INTO guro_messages (thread_id, sender_id, body, created_at, via_workspace) "
            "VALUES (?,?,?,?,?)",
            (thread_id, sender_id, body, now_str, via_workspace),
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
        # subscription_personal_cut=1 (29.08.2026, см. activate_subscription)
        # — оплачено на личный кошелёк владельца, не в бизнес-статистику.
        active_subs = self._conn.execute(
            "SELECT COUNT(*) FROM guro_users WHERE subscription_status=? AND subscription_expires_at > ? "
            "AND subscription_personal_cut != 1",
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

    # --- вакансии (Фаза 4, 12.08.2026; переработано 26.08.2026 по ТЗ
    # "Recruitment — ВАКАНСИИ") ------------------------------------------

    _VACANCY_EDITABLE_FIELDS = (
        "title", "vertical", "grade", "position", "position_is_other", "location",
        "work_format", "employment_type", "salary_from", "salary_to", "salary_negotiable",
        "salary_visible", "description", "contact_method", "contact_url", "lang",
    )

    def create_vacancy(
        self, author_id: int, *, author_workspace: str, title: str, vertical: str | None = None,
        grade: str | None = None, position: str | None = None, position_is_other: bool = False,
        location: str | None = None, work_format: str | None = None, employment_type: str | None = None,
        salary_from: float | None = None, salary_to: float | None = None,
        salary_negotiable: bool = False, salary_visible: bool = False, description: str | None = None,
        contact_method: str = GC.VACANCY_CONTACT_GURO_ID, contact_url: str | None = None,
        duration_days: int = GC.VACANCY_DURATION_DEFAULT, lang: str = "ru",
        published_by_user_id: int | None = None,
    ) -> sqlite3.Row:
        """author_id — владелец лимитов/показа (для author_workspace="company"
        это id компании, НЕ обязательно тот же человек, что реально нажал
        "Опубликовать" — см. published_by_user_id, ТЗ "Роли и команда",
        раздел 6, "какой конкретно участник команды это сделал")."""
        now = self._now()
        expires_at = GL.format_db_datetime(now + timedelta(days=duration_days))
        cur = self._conn.execute(
            "INSERT INTO guro_vacancies (author_id, author_workspace, title, vertical, grade, position, "
            "position_is_other, location, work_format, employment_type, salary_from, salary_to, "
            "salary_negotiable, salary_visible, description, contact_method, contact_url, "
            "duration_days, expires_at, lang, status, created_at, published_by_user_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (author_id, author_workspace, title, vertical, grade, position,
             1 if position_is_other else 0, location, work_format, employment_type, salary_from, salary_to,
             1 if salary_negotiable else 0, 1 if salary_visible else 0, description, contact_method, contact_url,
             duration_days, expires_at, lang, GC.VACANCY_STATUS_ACTIVE, GL.format_db_datetime(now),
             published_by_user_id or author_id),
        )
        self._conn.commit()
        vacancy = self._conn.execute("SELECT * FROM guro_vacancies WHERE id=?", (cur.lastrowid,)).fetchone()
        if position_is_other and position:
            self.log_vacancy_other_position(vacancy["id"], vertical, grade, position)
        return vacancy

    def toggle_vacancy_bookmark(self, user_id: int, vacancy_id: int) -> bool | None:
        """Ставит/снимает закладку, возвращает НОВОЕ состояние (True —
        сохранено). None — вакансии не существует (чтобы ручка отдала 404,
        а не молча создавала закладку на мусорный id)."""
        if self.get_vacancy(vacancy_id) is None:
            return None
        row = self._conn.execute(
            "SELECT id FROM guro_vacancy_bookmarks WHERE user_id=? AND vacancy_id=?",
            (user_id, vacancy_id),
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO guro_vacancy_bookmarks (user_id, vacancy_id, created_at) VALUES (?,?,?)",
                (user_id, vacancy_id, self._now_str()),
            )
            self._conn.commit()
            return True
        self._conn.execute("DELETE FROM guro_vacancy_bookmarks WHERE id=?", (row["id"],))
        self._conn.commit()
        return False

    def bookmarked_vacancy_ids(self, user_id: int) -> set[int]:
        """Все закладки пользователя одним запросом — чтобы список вакансий
        не делал по запросу на карточку (N+1)."""
        rows = self._conn.execute(
            "SELECT vacancy_id FROM guro_vacancy_bookmarks WHERE user_id=?", (user_id,),
        ).fetchall()
        return {r["vacancy_id"] for r in rows}

    def log_vacancy_other_position(self, vacancy_id: int, vertical: str | None, grade: str | None, text: str) -> None:
        """"Другое" в поле Должность (раздел 3, п.4 ТЗ) — не попадает сразу
        в справочник, копится тут для последующего централизованного review."""
        self._conn.execute(
            "INSERT INTO guro_vacancy_other_positions (vacancy_id, vertical, grade, text, created_at) "
            "VALUES (?,?,?,?,?)",
            (vacancy_id, vertical, grade, text, self._now_str()),
        )
        self._conn.commit()

    def _vacancy_matches_query(self, row, query_lower: str) -> bool:
        haystack = " ".join(filter(None, [row["title"], row["description"]])).lower()
        return query_lower in haystack

    # Общий SELECT для всех выборок вакансий (26.08.2026, ТЗ "Компания. каб",
    # раздел 4 — "приоритет верифицированных компаний в сортировке доски") —
    # JOIN с кабинетом компании-автора даёт is_verified_company/
    # author_company_types на КАЖДОЙ строке, независимо от того, кто/как
    # вызывает выборку (доска, "мои вакансии", одна карточка), иначе
    # sqlite3.Row["is_verified_company"] падал бы KeyError там, где джойна нет.
    _VACANCY_SELECT = (
        "SELECT v.*, COALESCE(cp.verified, 0) AS is_verified_company, "
        "COALESCE(cp.company_types, '') AS author_company_types "
        "FROM guro_vacancies v "
        "LEFT JOIN guro_company_profiles cp "
        "ON v.author_workspace='company' AND cp.user_id = v.author_id"
    )

    def list_vacancies(
        self, *, lang: str | None = None, vertical: str | None = None, grade: str | None = None,
        position: str | None = None, query: str | None = None, company_type: str | None = None,
        limit: int = GC.VACANCY_LIST_LIMIT, only_ids: set[int] | None = None,
    ) -> tuple[list[sqlite3.Row], bool]:
        """Доска вакансий (раздел 3.2, "устойчивость к неточному
        тегированию") — если задан query (текстовый поиск), запись
        попадает в выдачу при совпадении СТРУКТУРНЫХ фильтров (вертикаль/
        грейд/должность) ИЛИ текста в названии/описании — не строгое AND.
        Без query — обычные AND-фильтры, как раньше. company_type — фильтр
        по тегу "Тип компании" автора (ТЗ "Компания. каб", раздел 5),
        применяется как жёсткий AND независимо от query (структурный тег,
        не текст для нечёткого поиска). Сортировка: вакансии
        верифицированных компаний — выше остальных (раздел 4 ТЗ), внутри
        группы — по дате. Возвращает (результаты, truncated)."""
        # only_ids (03.09.2026) — фильтр доски по закладкам. Пустое
        # множество означает "закладок нет вообще": выходим сразу, иначе
        # получился бы невалидный SQL "IN ()".
        if only_ids is not None and not only_ids:
            return [], False
        now_str = self._now_str()
        sql = self._VACANCY_SELECT + " WHERE v.status=? AND (v.expires_at IS NULL OR v.expires_at > ?)"
        params: list = [GC.VACANCY_STATUS_ACTIVE, now_str]
        if only_ids is not None:
            sql += f" AND v.id IN ({','.join('?' * len(only_ids))})"
            params.extend(sorted(only_ids))
        if lang:
            sql += " AND v.lang=?"
            params.append(lang)
        query_lower = query.strip().lower() if query else None
        if not query_lower:
            if vertical:
                sql += " AND v.vertical=?"
                params.append(vertical)
            if grade:
                sql += " AND v.grade=?"
                params.append(grade)
            if position:
                sql += " AND v.position=?"
                params.append(position)
        # v.id DESC — тай-брейкер (created_at секундной точности, при быстрой
        # публикации нескольких вакансий подряд в один и тот же timestamp
        # порядок без него не детерминирован).
        sql += " ORDER BY is_verified_company DESC, v.created_at DESC, v.id DESC"
        rows = self._conn.execute(sql, params).fetchall()

        if query_lower:
            def structured_match(row) -> bool:
                if vertical and row["vertical"] != vertical:
                    return False
                if grade and row["grade"] != grade:
                    return False
                if position and row["position"] != position:
                    return False
                return bool(vertical or grade or position)

            rows = [r for r in rows if structured_match(r) or self._vacancy_matches_query(r, query_lower)]

        if company_type:
            rows = [
                r for r in rows
                if company_type in [s.strip() for s in (r["author_company_types"] or "").split(",") if s.strip()]
            ]

        truncated = len(rows) > limit
        return rows[:limit], truncated

    def list_my_vacancies(self, author_id: int) -> list[sqlite3.Row]:
        """Все свои — включая закрытые/на паузе, для управления (в отличие
        от list_vacancies, которая отдаёт только активные для чужого просмотра).
        Участник команды компании (27.08.2026, ТЗ "Роли и команда") видит
        ОБЩИЕ вакансии компании (author_id=company_id) в ДОПОЛНЕНИЕ к своим
        личным/рекрутерским — не два разных экрана, один общий список."""
        membership = self.get_company_membership(author_id)
        if membership:
            return self._conn.execute(
                self._VACANCY_SELECT + " WHERE v.author_id IN (?, ?) ORDER BY v.created_at DESC, v.id DESC",
                (author_id, membership["company_id"]),
            ).fetchall()
        return self._conn.execute(
            self._VACANCY_SELECT + " WHERE v.author_id=? ORDER BY v.created_at DESC, v.id DESC", (author_id,)
        ).fetchall()

    def vacancy_access_allowed(self, row, acting_user_id: int) -> bool:
        """Раздел 2 ТЗ "Роли и команда" — вакансия от лица компании доступна
        для управления ЛЮБОМУ участнику команды (Владелец и Админ/Рекрутер
        имеют одинаковые права на общие вакансии), не только тому, кто её
        опубликовал."""
        if row["author_id"] == acting_user_id:
            return True
        if row["author_workspace"] == "company":
            return self.get_company_role(row["author_id"], acting_user_id) is not None
        return False

    def get_vacancy(self, vacancy_id: int) -> sqlite3.Row | None:
        return self._conn.execute(self._VACANCY_SELECT + " WHERE v.id=?", (vacancy_id,)).fetchone()

    def increment_vacancy_views(self, vacancy_id: int, viewer_id: int) -> None:
        """Считает только чужие просмотры (не накручивает счётчик автору,
        когда он сам открывает свою вакансию — раздел 4, "Счётчик просмотров")."""
        row = self.get_vacancy(vacancy_id)
        if row is None or row["author_id"] == viewer_id:
            return
        self._conn.execute(
            "UPDATE guro_vacancies SET views_count=views_count+1 WHERE id=?", (vacancy_id,),
        )
        self._conn.commit()

    def edit_vacancy(self, vacancy_id: int, author_id: int, fields: dict) -> sqlite3.Row | None:
        """Поднимает ValueError('UNKNOWN_FIELD') на неразрешённое поле.
        None — вакансии нет или редактировать нельзя (не автор и не участник
        той же компании, см. vacancy_access_allowed)."""
        row = self.get_vacancy(vacancy_id)
        if row is None or not self.vacancy_access_allowed(row, author_id):
            return None
        unknown = set(fields) - set(self._VACANCY_EDITABLE_FIELDS)
        if unknown:
            raise ValueError("UNKNOWN_FIELD")
        if not fields:
            return row
        set_clause = ", ".join(f"{k}=?" for k in fields)
        self._conn.execute(
            f"UPDATE guro_vacancies SET {set_clause} WHERE id=?",
            (*fields.values(), vacancy_id),
        )
        self._conn.commit()
        return self.get_vacancy(vacancy_id)

    def _set_vacancy_status(self, vacancy_id: int, author_id: int, status: str, *, reason: str | None = None) -> bool:
        row = self.get_vacancy(vacancy_id)
        if row is None or not self.vacancy_access_allowed(row, author_id):
            return False
        self._conn.execute(
            "UPDATE guro_vacancies SET status=?, closed_reason=? WHERE id=?",
            (status, reason, vacancy_id),
        )
        self._conn.commit()
        return True

    def pause_vacancy(self, vacancy_id: int, author_id: int) -> bool:
        return self._set_vacancy_status(vacancy_id, author_id, GC.VACANCY_STATUS_PAUSED)

    def resume_vacancy(self, vacancy_id: int, author_id: int) -> bool:
        return self._set_vacancy_status(vacancy_id, author_id, GC.VACANCY_STATUS_ACTIVE)

    def close_vacancy(self, vacancy_id: int, author_id: int, *, reason: str | None = None) -> bool:
        """False — вакансии нет или закрывает не автор (проверяем тут, а не
        в API, чтобы правило жило рядом с данными)."""
        return self._set_vacancy_status(vacancy_id, author_id, GC.VACANCY_STATUS_CLOSED, reason=reason)

    def extend_vacancy(self, vacancy_id: int, author_id: int, duration_days: int) -> bool:
        """Продлить — срок считается ЗАНОВО от текущего момента (не
        накопительно к старому expires_at)."""
        row = self.get_vacancy(vacancy_id)
        if row is None or not self.vacancy_access_allowed(row, author_id):
            return False
        expires_at = GL.format_db_datetime(self._now() + timedelta(days=duration_days))
        self._conn.execute(
            "UPDATE guro_vacancies SET duration_days=?, expires_at=?, status=? WHERE id=?",
            (duration_days, expires_at, GC.VACANCY_STATUS_ACTIVE, vacancy_id),
        )
        self._conn.commit()
        return True

    # --- отклики на вакансии, мини-ATS (раздел 5 ТЗ, 26.08.2026) ----------

    def create_vacancy_response(self, vacancy_id: int, candidate_id: int, message: str | None) -> sqlite3.Row:
        """Поднимает ValueError: NOT_FOUND / NOT_ACTIVE / SELF_RESPONSE /
        ALREADY_RESPONDED (уникальный индекс на (vacancy_id, candidate_id))."""
        row = self.get_vacancy(vacancy_id)
        if row is None:
            raise ValueError("NOT_FOUND")
        if row["status"] != GC.VACANCY_STATUS_ACTIVE:
            raise ValueError("NOT_ACTIVE")
        if self.vacancy_access_allowed(row, candidate_id):
            raise ValueError("SELF_RESPONSE")
        try:
            cur = self._conn.execute(
                "INSERT INTO guro_vacancy_responses (vacancy_id, candidate_id, status, message, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (vacancy_id, candidate_id, GC.RESPONSE_STATUS_NEW, message, self._now_str(), self._now_str()),
            )
        except sqlite3.IntegrityError:
            raise ValueError("ALREADY_RESPONDED") from None
        self._conn.commit()
        return self._conn.execute(
            "SELECT * FROM guro_vacancy_responses WHERE id=?", (cur.lastrowid,)
        ).fetchone()

    def get_vacancy_response(self, response_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM guro_vacancy_responses WHERE id=?", (response_id,)
        ).fetchone()

    def count_vacancy_responses(self, vacancy_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM guro_vacancy_responses WHERE vacancy_id=?", (vacancy_id,)
        ).fetchone()
        return row["n"]

    def list_vacancy_responses(self, vacancy_id: int, *, status: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM guro_vacancy_responses WHERE vacancy_id=?"
        params: list = [vacancy_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        return self._conn.execute(sql, params).fetchall()

    def list_responses_for_owner(self, author_id: int, *, status: str | None = None) -> list[sqlite3.Row]:
        """Агрегированные отклики по ВСЕМ вакансиям рекрутера/компании
        (раздел 5.5, "Отклики" на главном экране кабинета) — с полями самой
        вакансии подмешанными через JOIN, чтобы фронт мог показать метку
        вакансии на каждой карточке без отдельных запросов. Участник команды
        компании (27.08.2026, ТЗ "Роли и команда") видит отклики ОБЩИХ
        вакансий компании в дополнение к своим личным/рекрутерским."""
        membership = self.get_company_membership(author_id)
        author_ids = (author_id, membership["company_id"]) if membership else (author_id, author_id)
        sql = (
            "SELECT r.*, v.title AS vacancy_title FROM guro_vacancy_responses r "
            "JOIN guro_vacancies v ON v.id = r.vacancy_id WHERE v.author_id IN (?, ?)"
        )
        params: list = list(author_ids)
        if status:
            sql += " AND r.status=?"
            params.append(status)
        sql += " ORDER BY r.created_at DESC"
        return self._conn.execute(sql, params).fetchall()

    def count_responses_since(
        self, author_id: int, since_dt: datetime, *, workspace: str | None = None,
    ) -> int:
        """"Откликов за 7 дней" (панель "Характеристика", 2.3 / раздел 3 ТЗ
        "Компания. каб") — та же агрегация свои+компания, что у
        list_responses_for_owner (см. выше), просто COUNT с отсечкой по дате
        вместо полной выборки. Раньше был хардкод 0 (структурированной
        механики "Отклики" ещё не было, см. старый комментарий в
        _recruiter_summary) — сама механика уже реализована (guro_vacancy_
        responses), просто забыли прокинуть сюда при её появлении."""
        membership = self.get_company_membership(author_id)
        author_ids = (author_id, membership["company_id"]) if membership else (author_id, author_id)
        # 06.09.2026 («компания.pdf», стр. 2): по author_id кабинеты не
        # различаются — у владельца-одиночки company_id равен его же
        # user_id, и отклик на вакансию рекрутера засчитывался компании.
        # Разделяет их только author_workspace.
        sql = (
            "SELECT COUNT(*) AS n FROM guro_vacancy_responses r "
            "JOIN guro_vacancies v ON v.id = r.vacancy_id "
            "WHERE v.author_id IN (?, ?) AND r.created_at >= ?"
        )
        params: list = [*author_ids, GL.format_db_datetime(since_dt)]
        if workspace == "company":
            sql += " AND v.author_workspace = 'company'"
        elif workspace == "recruiter":
            # Всё, что не компания: вакансии кабинета рекрутера и
            # опубликованные из личного профиля до его появления. Так ни
            # один отклик не теряется и не считается дважды.
            sql += " AND (v.author_workspace IS NULL OR v.author_workspace <> 'company')"
        row = self._conn.execute(
            sql,
            tuple(params),
        ).fetchone()
        return row["n"]

    def update_vacancy_response_status(self, response_id: int, author_id: int, status: str) -> sqlite3.Row | None:
        """Поднимает ValueError('INVALID_STATUS'). None — отклика нет или
        статус меняет тот, у кого нет доступа к вакансии (владелец/участник
        той же компании, см. vacancy_access_allowed)."""
        if status not in GC.RESPONSE_STATUSES:
            raise ValueError("INVALID_STATUS")
        row = self._conn.execute(
            "SELECT r.*, v.author_id AS v_author_id, v.author_workspace AS v_author_workspace "
            "FROM guro_vacancy_responses r JOIN guro_vacancies v ON v.id=r.vacancy_id WHERE r.id=?",
            (response_id,),
        ).fetchone()
        if row is None or not self.vacancy_access_allowed(
            {"author_id": row["v_author_id"], "author_workspace": row["v_author_workspace"]}, author_id,
        ):
            return None
        self._conn.execute(
            "UPDATE guro_vacancy_responses SET status=?, updated_at=? WHERE id=?",
            (status, self._now_str(), response_id),
        )
        self._conn.commit()
        return self.get_vacancy_response(response_id)

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
