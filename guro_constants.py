"""Константы модуля GURO ID (репутация/партнёрства). Отдельно от constants.py,
т.к. это самостоятельный модуль поверх старого функционала бота (см. ТЗ)."""
from __future__ import annotations

# --- Формула рейтинга v2 (25.08.2026, ТЗ "Сделка, формула рейтинга,
# анти-абьюз") — полностью заменяет линейную модель 15-16.08.2026
# (BASE_REPUTATION=0 + фиксированный CONFIRMATION_GAIN=+1/сделка) на
# взвешенную формулу с диминишингом повторов, типом сделки, крипто-
# бонусами и штрафами, сжатую в шкалу 0-100 через экспоненту.
# По прямому решению владельца (25.08.2026) вся ИСТОРИЯ партнёрств
# пересчитана под эту формулу с нуля — см. migrate_reputation_formula_v2.py.
# Чистые функции формулы — guro_logic.py; поштучная запись/применение —
# guro_storage.py (create_partnership/respond_partnership/submit_rating/
# recompute_total_w).

PARTNERSHIP_TYPE_DEAL = "deal"
PARTNERSHIP_TYPE_HIRE = "hire"
PARTNERSHIP_TYPES = (PARTNERSHIP_TYPE_DEAL, PARTNERSHIP_TYPE_HIRE)

# 5.1 — базовые очки за подтверждённое партнёрство.
PARTNERSHIP_BASE_POINTS = {
    PARTNERSHIP_TYPE_DEAL: 10.0,
    PARTNERSHIP_TYPE_HIRE: 15.0,
}

# 5.2 — диминишинг повторных контрагентов: 1-е подтверждённое партнёрство с
# уникальным контрагентом = 100% базовых очков, каждое следующее = 20%,
# максимум 3 засчитанных повтора (т.е. 4-е партнёрство с тем же человеком —
# последнее, что ещё даёт очки; 5-е и далее — 0). Защита от фарма рейтинга
# через договорные сделки между двумя аккаунтами.
PARTNERSHIP_REPEAT_DECAY = 0.20
PARTNERSHIP_REPEAT_MAX_COUNTED = 4  # 1 полное + 3 повтора по 20%

# 5.3 — сжатие суммы взвешенных очков (W) в шкалу 0-100: R = 100×(1−e^(−W/40)).
REPUTATION_W_SCALE = 40.0
# Текстовые уровни рейтинга (5.3, "например Bronze/Silver/Gold/Platinum") —
# границы подобраны так, чтобы Platinum требовал заметного числа сделок
# (R=90 достигается при W≈92, то есть больше 9 базовых "deal"-партнёрств
# без диминишинга — ощутимый порог, не с первой же сделки).
REPUTATION_TIERS = (
    (0.0, "Bronze"),
    (40.0, "Silver"),
    (70.0, "Gold"),
    (90.0, "Platinum"),
)

# 5.4 — бонусный множитель за верифицированный ончейн крипто-хеш сделки.
# ТЗ даёт диапазон ×1.3–1.5 без правила выбора внутри него — взята середина
# как приближение (тюнится вручную, тот же приём, что STARS_TO_USD_RATE).
CRYPTO_VERIFIED_MULTIPLIER = 1.4
# Если один из адресов транзакции совпадает с верифицированным адресом
# компании (5.5) — множитель ЗАМЕНЯЕТ обычный (не перемножается с ним).
CRYPTO_COMPANY_MULTIPLIER = 2.0
# Логарифмическое сглаживание суммы сделки (5.4, последний пункт) — ДОПУЩЕНИЕ
# (в ТЗ явно не сказано, привязано ли оно к верификации): применяется
# ТОЛЬКО когда крипто-хеш реально верифицирован ончейн — самозаявленная
# сумма без всякой проверки была бы тривиальным вектором фарма рейтинга,
# что противоречило бы всему смыслу антифрода раздела 5.2. Добавочные очки =
# коэффициент × log10(1+сумма_в_USD), это добавка к очкам, не множитель.
CRYPTO_AMOUNT_LOG_COEFFICIENT = 1.0
# Поддерживаемые сети для верификации хеша — определяет, какой explorer API
# дёргать (guro_chain_verify.py). Адреса Tron/EVM визуально неотличимы по
# формату хеша у ETH/BSC (оба EVM, 0x+64 hex) — поэтому сеть выбирается
# пользователем явно в форме, а не угадывается.
TX_NETWORKS = ("tron", "ethereum", "bsc")

# 5.6 — бонус за стаж, теперь часть W (раньше был частью стартовой
# репутации, отдельно от сделок). +0.05/день, максимум +5 суммарно.
TENURE_BONUS_PER_DAY = 0.05
TENURE_BONUS_MAX = 5.0

# 5.7 — штраф за проблемную сделку. ТЗ даёт диапазон 15–20 без правила
# выбора — взята середина, тот же приём, что у CRYPTO_VERIFIED_MULTIPLIER.
PARTNERSHIP_PENALTY_POINTS = 17.5

# 6.1 — оценка партнёрства (Шаг 2), доступна только ПОСЛЕ подтверждения
# факта (Шаг 1 — уже существующий accept/decline). Каждая сторона независимо
# и не обязательно ставит одну из трёх оценок.
RATING_SUCCESS = "success"
RATING_NUANCE = "nuance"
RATING_PROBLEMATIC = "problematic"
RATING_VERDICTS = (RATING_SUCCESS, RATING_NUANCE, RATING_PROBLEMATIC)
RATING_COMMENT_MAX = 500
# Anti-retaliation: обе оценки скрыты друг от друга, пока не оставят ОБЕ
# стороны, либо не истечёт этот срок с момента подтверждения партнёрства.
RATING_REVEAL_TIMEOUT_DAYS = 14

# 7.3 — эвристика подозрительного скрапинга: N просмотров за M минут одним
# аккаунтом -> флаг на РУЧНУЮ проверку (ТЗ явно требует ручную проверку +
# возможность временной заморозки админом, не авто-бан).
SCRAPING_BURST_COUNT = 15
SCRAPING_BURST_MINUTES = 10
# Длительность ручной заморозки аккаунта из /admin (7.3) — админ может
# продлить, повторно применив действие.
ACCOUNT_FREEZE_HOURS = 24

# --- Тарифы и лимиты (27.08.2026, ТЗ "Тарифы и лимиты") -------------------
# Сам документ прямо помечен как "гипотеза для MVP, не проверенная на
# реальных платежах цена" и требует хранить значения конфигурируемыми, не
# хардкодить (раздел 3). Компромисс: дефолты — константы тут (тот же
# принцип, что весь остальной прайсинг модуля, включая STARS_TO_USD_RATE),
# а РЕАЛЬНЫЕ действующие значения дневных/одновременных лимитов можно
# переопределить без релиза через guro_config (глобально) и
# guro_user_limit_overrides (точечно на конкретный аккаунт) — см.
# GuroStorage.get_config/get_effective_limit и handlers/admin_guro.py
# (команда /guro_limit). Цены подписок (раздел 1) НЕ переведены на этот
# слой — весь прайсинг сессии до сих пор жил в константах ниже
# (SUBSCRIPTION_PLANS и т.п.), делать из одних только НОВЫХ цифр
# исключение было бы непоследовательно; поменять цену — по-прежнему правка
# константы и деплой, как раньше.

# 2.1 — просмотр чужих профилей/день. Личный Pro НЕ лимитируется отдельно
# (см. _check_profile_view_limit в guro_id_api.py — рейт-лимит применяется
# только к подписчикам Рекрутер/Компания).
LIMIT_VIEWS_PER_DAY_RECRUITER = 30
LIMIT_VIEWS_PER_DAY_COMPANY_BASIC = 30
LIMIT_VIEWS_PER_DAY_COMPANY_PRO = 50

# 2.2 — новые заявки на партнёрство/найм в день (НЕ путать с RATE_LIMIT_HOURS
# выше — тот лимитирует повтор ОДНОЙ И ТОЙ ЖЕ пары контрагентов, этот —
# общее число НОВЫХ связей в день, узкое место фарма рейтинга).
LIMIT_NEW_REQUESTS_PER_DAY_PERSONAL = 10
LIMIT_NEW_REQUESTS_PER_DAY_RECRUITER = 20
LIMIT_NEW_REQUESTS_PER_DAY_COMPANY = 30

# 2.3 — вакансии: дневной лимит НОВЫХ публикаций (единый для всех, у кого
# вообще есть право публиковать) + потолок ОДНОВРЕМЕННО активных
# (коммерческий рычаг, растёт с тарифом; считается ОТДЕЛЬНО на каждый
# кабинет — см. GuroStorage.count_active_vacancies(workspace=...)).
LIMIT_NEW_VACANCIES_PER_DAY = 3
LIMIT_ACTIVE_VACANCIES_RECRUITER = 10
LIMIT_ACTIVE_VACANCIES_COMPANY_BASIC = 20
LIMIT_ACTIVE_VACANCIES_COMPANY_PRO = 50

# Ключи для guro_config/guro_user_limit_overrides (один и тот же строковый
# ключ используется и глобальным конфигом, и точечным оверрайдом на
# аккаунт — get_effective_limit сначала проверяет оверрайд, потом конфиг).
LIMIT_KEY_VIEWS_RECRUITER = "views_per_day.recruiter"
LIMIT_KEY_VIEWS_COMPANY_BASIC = "views_per_day.company_basic"
LIMIT_KEY_VIEWS_COMPANY_PRO = "views_per_day.company_pro"
LIMIT_KEY_REQUESTS_PERSONAL = "new_requests_per_day.personal"
LIMIT_KEY_REQUESTS_RECRUITER = "new_requests_per_day.recruiter"
LIMIT_KEY_REQUESTS_COMPANY = "new_requests_per_day.company"
LIMIT_KEY_NEW_VACANCIES = "new_vacancies_per_day"
LIMIT_KEY_ACTIVE_VACANCIES_RECRUITER = "active_vacancies.recruiter"
LIMIT_KEY_ACTIVE_VACANCIES_COMPANY_BASIC = "active_vacancies.company_basic"
LIMIT_KEY_ACTIVE_VACANCIES_COMPANY_PRO = "active_vacancies.company_pro"
# Все ключи разом — для команды /guro_limit (валидация ввода + листинг).
LIMIT_KEYS = (
    LIMIT_KEY_VIEWS_RECRUITER, LIMIT_KEY_VIEWS_COMPANY_BASIC, LIMIT_KEY_VIEWS_COMPANY_PRO,
    LIMIT_KEY_REQUESTS_PERSONAL, LIMIT_KEY_REQUESTS_RECRUITER, LIMIT_KEY_REQUESTS_COMPANY,
    LIMIT_KEY_NEW_VACANCIES,
    LIMIT_KEY_ACTIVE_VACANCIES_RECRUITER, LIMIT_KEY_ACTIVE_VACANCIES_COMPANY_BASIC,
    LIMIT_KEY_ACTIVE_VACANCIES_COMPANY_PRO,
)
# Раздел 2.4 ТЗ (потолок участников компании + лимит одобрений заявок/день)
# сознательно НЕ реализован в этом раунде — завязан на раздел "Команда"
# (роли/заявки на присоединение), которого в кодовой базе ещё нет (см. ТЗ
# "Компания. каб", раздел 7 — ссылается на отдельный "основное ТЗ").

# --- Тарифы (раздел 1 ТЗ, репрайсинг 27.08.2026) --------------------------
# Личный Pro: $6/мес, $50/год. Рекрутер Pro: $19/мес, $170/год. Компания
# теперь ДВА тира вместо одного (Basic/Pro) — реализованы как два отдельных
# "product" (company_basic/company_pro), та же generic-инфраструктура
# оплаты, что у guro_id/recruiter (см. _PRODUCT_PLANS в guro_id_api.py).
# Округление $->⭐ при STARS_TO_USD_RATE=0.015 до ближайших 50⭐ (тот же
# приём, что раньше — "красивое число", ТЗ прямо пишет "цена не проверена").
COMPANY_TIER_BASIC = "basic"
COMPANY_TIER_PRO = "pro"
COMPANY_TIERS = (COMPANY_TIER_BASIC, COMPANY_TIER_PRO)

# --- Роли и команда компании (27.08.2026, ТЗ "Роли и управление командой в
# кабинете 'Компания'") — ровно ДВЕ роли, без градации прав по функциям
# (раздел 2 ТЗ: должность человека — описательное поле, не ACL). Владелец
# может всё, что Админ/Рекрутер, плюс управляет составом команды/передаёт
# владение. "Компания" как сущность технически — тот же guro_company_profiles
# (PK user_id основателя ПРОДОЛЖАЕТ служить стабильным company_id даже после
# передачи владения другому человеку), поверх неё guro_company_members даёт
# многие-ко-многим людей и ролей.
COMPANY_ROLE_OWNER = "owner"
COMPANY_ROLE_ADMIN = "admin"
COMPANY_ROLES = (COMPANY_ROLE_OWNER, COMPANY_ROLE_ADMIN)

JOIN_REQUEST_PENDING = "pending"
JOIN_REQUEST_APPROVED = "approved"
JOIN_REQUEST_REJECTED = "rejected"
JOIN_REQUEST_STATUSES = (JOIN_REQUEST_PENDING, JOIN_REQUEST_APPROVED, JOIN_REQUEST_REJECTED)

# Раздел 3.4 ТЗ — потолок участников по тарифу ("до 5"/"до 20", это
# конкретное число ТЗ "Роли и команда", не "15-20" из общего прайсинга).
COMPANY_MEMBER_LIMIT_BASIC = 5
COMPANY_MEMBER_LIMIT_PRO = 20

# Раздел 3.5 ТЗ — не более 5 одобрений новых участников/день, независимо от
# тарифа (закрывает раздел 2.4 ТЗ "Тарифы и лимиты", сознательно отложенный
# в прошлом раунде до появления самой механики команды).
LIMIT_KEY_COMPANY_APPROVALS_PER_DAY = "company_approvals_per_day"
LIMIT_COMPANY_APPROVALS_PER_DAY = 5
LIMIT_KEYS = LIMIT_KEYS + (LIMIT_KEY_COMPANY_APPROVALS_PER_DAY,)

# Анти-фрод (ТЗ п.4, исходный план 04.08): не больше 1 новой заявки в сутки
# на пару, и подтверждения между свежими (<14 дней в комьюнити) аккаунтами
# не учитываются в рейтинге (видны, но помечены).
RATE_LIMIT_HOURS = 24
MIN_TENURE_DAYS_TO_COUNT = 14

# Тарифы подписки — "Личный Pro" (репрайсинг 27.08.2026, ТЗ "Тарифы и
# лимиты": $6/мес, $50/год ~30% скидки). При STARS_TO_USD_RATE=0.015:
# $6=400⭐ ровно, $50≈3333⭐ округлено до ближайших 50⭐ (3350). "yearly"
# дороже помесячной цены x12 (400*12=4800) продан со скидкой за 3350 —
# оба числа нужны фронту для зачёркнутой "полной" цены. Прежние цифры
# (650/6600, ориентир $10/$99 от 10.08.2026) заменены этим раундом —
# ТЗ прямо пишет "гипотеза, не проверенная на реальных платежах".
SUBSCRIPTION_PLANS = {
    "monthly": {
        "label": "Месяц",
        "duration_days": 30,
        "stars_price": 400,
    },
    "yearly": {
        "label": "Год",
        "duration_days": 365,
        "stars_price": 3350,
        "stars_price_full": 4800,  # 400*12 — "было бы" по помесячной цене, для скидочной плашки
    },
}

# Кабинет рекрутера (Фаза 3, 12.08.2026) — ОТДЕЛЬНАЯ подписка поверх
# базовой GURO ID. Репрайсинг 27.08.2026 (ТЗ "Тарифы и лимиты"): "Рекрутер
# Pro" $19/мес, $170/год (~25% скидки). $19/0.015≈1267⭐ округлено до 1250⭐,
# $170/0.015≈11333⭐ округлено до 11350⭐. "Полная" цена года = 1250*12=15000⭐.
RECRUITER_SUBSCRIPTION_PLANS = {
    "monthly": {
        "label": "Месяц",
        "duration_days": 30,
        "stars_price": 1250,
    },
    "yearly": {
        "label": "Год",
        "duration_days": 365,
        "stars_price": 11350,
        "stars_price_full": 15000,
    },
}

# Поля витрины рекрутера — редактируются ПРЯМО в Mini App (как
# EXTRA_PROFILE_FIELDS у личного профиля), т.к. другого способа их
# заполнить нет. "name"/"company"/"vertical"/"profession" здесь — СВОИ,
# независимые от анкеты бота (человек может представляться иначе в
# рабочем режиме, например "HR отдел GURO Labs"), не читаются из profiles.
RECRUITER_EXTRA_FIELDS = ("name", "company", "vertical", "profession", "cv_text", "website", "offering", "logo_url")

# Главный экран кабинета "Рекрутер" (ТЗ "Гуро рекрутер каб", 26.08.2026).
# Статус активности — отдельный от work_status личного профиля (2.4).
RECRUITER_ACTIVITY_HIRING = "hiring"
RECRUITER_ACTIVITY_NOT_HIRING = "not_hiring"
RECRUITER_ACTIVITY_VALUES = (RECRUITER_ACTIVITY_HIRING, RECRUITER_ACTIVITY_NOT_HIRING)

# Блок процентиля (2.5) — R_найм = 100×(1−e^(−W_найм/40)), та же формула
# сжатия, что и общий рейтинг (см. reputation_from_w), но W_найм считается
# ТОЛЬКО по подтверждённым партнёрствам с ptype="hire" этого пользователя
# (без бонуса за стаж — см. guro_storage.hire_w). Ступени округления —
# "топ-X%" вместо точного процента (ТЗ, п. 2.5 "Правила отображения").
RECRUITER_PERCENTILE_TIERS = ((95.0, "5"), (90.0, "10"), (75.0, "25"), (50.0, "50"))
# Минимальная выборка рекрутеров в вертикали (с хотя бы 1 наймом), чтобы
# вообще показывать блок процентиля — иначе он статистически бессмысленен.
RECRUITER_PERCENTILE_MIN_SAMPLE = 30

# Кабинет "Компания" (16.08.2026, по прямому запросу владельца) — ТРЕТИЙ
# воркспейс, параллельный Рекрутеру, той же архитектурой (сателлит-
# таблица, своя подписка). Разница по итогу обсуждения с владельцем:
# Компания — бренд-страница работодателя (лого/описание/сайт), Рекрутер —
# конкретный человек внутри неё (как LinkedIn Company Page vs Recruiter
# Profile). "name" здесь = название компании (не имя человека, как у
# рекрутера) — то же имя поля намеренно, для единообразия остальной
# generic-инфраструктуры (get_company_extra/set_company_profile_field).
# Компания — раньше ЕДИНАЯ подписка/цена, с 27.08.2026 (ТЗ "Тарифы и
# лимиты") ДВА тира: Basic (до 5 участников, $49/мес, $420/год) и Pro (до
# 15-20 участников, $99/мес, $850/год) — реализованы как два ОТДЕЛЬНЫХ
# "product" (company_basic/company_pro) поверх той же generic-платёжной
# цепочки, что guro_id/recruiter, а не как параметр внутри одного продукта
# (минимально инвазивно: не трогает _PRODUCT_PLANS/handle_subscribe/
# handle_crypto_webhook/guro_payments.py — просто два новых ключа словаря).
# Обе пишут в ОДНУ И ТУ ЖЕ guro_company_profiles (один кабинет, один
# аккаунт), тир фиксируется отдельным полем company_tier при активации
# (см. GuroStorage.activate_company_subscription).
# $49/0.015≈3267⭐ округлено до 3250⭐, $420/0.015=28000⭐ ровно.
COMPANY_BASIC_SUBSCRIPTION_PLANS = {
    "monthly": {
        "label": "Месяц",
        "duration_days": 30,
        "stars_price": 3250,
    },
    "yearly": {
        "label": "Год",
        "duration_days": 365,
        "stars_price": 28000,
        "stars_price_full": 39000,  # 3250*12
    },
}
# $99/0.015=6600⭐ ровно, $850/0.015≈56667⭐ округлено до 56650⭐.
COMPANY_PRO_SUBSCRIPTION_PLANS = {
    "monthly": {
        "label": "Месяц",
        "duration_days": 30,
        "stars_price": 6600,
    },
    "yearly": {
        "label": "Год",
        "duration_days": 365,
        "stars_price": 56650,
        "stars_price_full": 79200,  # 6600*12
    },
}
COMPANY_EXTRA_FIELDS = (
    "name", "vertical", "website", "description", "logo_url",
    # 26.08.2026, ТЗ "Компания. каб" (визуальная идентичность/верификация):
    # обложка баннера + тип(ы) компании (множественный выбор + "Другое").
    "cover_url", "company_types", "company_type_other",
)

# "Тип компании" (раздел 5 ТЗ) — тег/фильтр, НЕ меняет структуру кабинета.
# Множественный выбор, хранится comma-join'ом в company_types (тот же приём,
# что cv_verticals). "Другое" — отдельное поле company_type_other, логируется
# в guro_company_other_types (см. GuroStorage.log_company_other_type), по
# аналогии со справочником должностей вакансий.
COMPANY_TYPES = (
    "operator_casino", "bookmaker", "cpa_network", "hr_agency",
    "media_buying", "b2b_platform", "investor_fund",
)

# Курс Stars -> USD НЕ публикуется Telegram официально как единая ставка —
# только цена IAP-пакетов (Apple/Google), а она сама плавает по размеру
# пакета (~$0.013-0.02/⭐ в разных бандлах). Это осознанно приближённая,
# вручную поддерживаемая константа для расчёта крипто-цены — не живой курс.
# Пересматривать вручную, если Telegram ощутимо поменяет цены Stars.
STARS_TO_USD_RATE = 0.015
CRYPTO_ASSET = "USDT"

# 29.08.2026 — позиция кольца распределения новых крипто-инвойсов между
# двумя токенами CryptoBot (см. config.cryptobot_api_token_new и
# guro_id_api._pick_crypto_token). Ключ в guro_config (get_config/set_config).
CRYPTO_TOKEN_CYCLE_KEY = "crypto_token_cycle.position"

PARTNERSHIP_STATUS_PENDING = "pending"
PARTNERSHIP_STATUS_CONFIRMED = "confirmed"
PARTNERSHIP_STATUS_DECLINED = "declined"

SUBSCRIPTION_ACTIVE = "active"
SUBSCRIPTION_INACTIVE = "inactive"

# Статус-тег участника в чате (Bot API 22.7+, setChatMemberTag) — показывает
# АКТИВНУЮ ПОДПИСКУ GURO ID прямо у имени в сообщениях (не сам факт наличия
# анкеты/захода в Mini App — это дефолтное условие для всех в сообществе,
# ничего не выделяет). Доступно ЛЮБОМУ обычному участнику (не только
# админам, в отличие от custom title), поэтому не упирается в лимит ~50
# админов на группу. Максимум 16 симв., эмодзи запрещены Bot API
# (см. guro_tags.py).
GURO_TAG = "GURO ID"
GURO_TAGS = (GURO_TAG,)

# Приватность (10.08.2026, переведено на opt-in 10.08.2026 вечером,
# расширено 10.08.2026 под редизайн профиля): владелец профиля решает в
# Mini App, что из анкеты видно чужим в поиске. По умолчанию НИЧЕГО не
# видно (все флаги = 0/False) — участник сам включает то, что хочет
# показать. Партнёрства (с кем сотрудничал) и username показываются
# ВСЕГДА, независимо от этих тумблеров — это ядро смысла GURO ID
# (подтверждение репутации через сотрудничество) и необходимый минимум
# для идентификации в поиске.
#
# Тумблеры сгруппированы ПО РАЗДЕЛАМ нового профиля (не по каждому полю
# анкеты по отдельности — иначе было бы 12+ тумблеров вместо 9):
# show_tenure    -> joined_community_at + days_in_community (стаж, одно и то же)
# show_reputation-> reputation_score (экран "Мой рейтинг")
# show_cv        -> cv_text (экран "Моё CV")
# show_contacts  -> linkedin + website (экран "Мои контакты"; username/Telegram — всегда)
# show_offers    -> looking_for + offering (экран "Мои офферы", оба сразу — это пара "ищу/предлагаю")
PRIVACY_FIELDS = (
    "show_name", "show_company", "show_vertical", "show_profession",
    "show_tenure", "show_reputation",
    "show_cv", "show_contacts", "show_offers",
)

# Редизайн профиля (10.08.2026) — 3 НОВЫХ поля, которых нет в анкете бота
# (та живёт в общей таблице profiles, её не трогаем): резюме-текст, сайт,
# "чем полезен". В отличие от полей анкеты (только чтение в Mini App,
# источник — бот) эти поля редактируются ПРЯМО в Mini App, т.к. никакого
# другого способа их заполнить не существует. "Я ищу" НЕ входит сюда —
# уже есть готовое поле profiles.request ("что для вас сейчас актуально"),
# отдаётся как "looking_for" в API, редактируется только через анкету бота.
EXTRA_PROFILE_FIELDS = ("cv_text", "website", "offering", "looking_for")

# Статус трудоустройства (10.08.2026) — публичный маркер вроде "Open to
# Work" в LinkedIn: виден ВСЕМ бесплатно (даже без подписки просматривающего)
# и при обычном поиске, и через QR — по решению владельца статус должен
# работать как приманка, а не как платный контент. Поэтому НЕ входит в
# PRIVACY_FIELDS/_PRIVACY_FIELD_MAP — своя отдельная колонка с 4-м
# состоянием "выкл" (NULL), которое и есть скрытие.
WORK_STATUS_LOOKING = "looking"
WORK_STATUS_NEUTRAL = "neutral"
WORK_STATUS_WORKING = "working"
WORK_STATUS_VALUES = (WORK_STATUS_LOOKING, WORK_STATUS_NEUTRAL, WORK_STATUS_WORKING)

# QR-код профиля (10.08.2026): кодирует deep-link `t.me/<bot>?start=guro_
# <user_id>` — НЕ прямую ссылку на Mini App (та требует отдельной
# регистрации short name через @BotFather, которой у бота сейчас нет).
# Сканирующий получает сообщение с web_app-кнопкой в чат с ботом; открытие
# карточки целиком по-прежнему подчиняется обычному пейволлу поиска
# (нужна подписка СМОТРЯЩЕГО, не хозяина QR).
QR_PAYLOAD_PREFIX = "guro_"

# Directory-поиск по описанию (10.08.2026) — "нужен менеджер в крипто" ->
# список ВСЕХ, у кого совпадение с полями, которые они САМИ открыли
# тумблерами приватности (см. guro_id_api._DIRECTORY_TEXT_FIELDS). Целиком
# платная фича по решению владельца — без подписки просматривающего
# эндпойнт не отдаёт результатов вообще, даже тизером (в отличие от
# точного /api/search по юзернейму). Лимит — чтобы не отдавать разом всю
# базу при широком запросе (например один общий популярный тег).
DIRECTORY_RESULTS_LIMIT = 30
DIRECTORY_QUERY_MAX_KEYWORDS = 10

# Личные сообщения внутри прилы (Фаза 1, 11.08.2026) — «написать мне» +
# «Мои сообщения». Правило доступа: писать ПЕРВЫМ (создавать новый тред)
# может только тот, у кого активна подписка GURO ID (== он уже видел
# полный, не тизерный профиль собеседника — та же проверка, что в
# handle_search). Отвечать в уже созданном треде может любой, подписка не
# нужна — иначе истёкшая подписка обрывала бы уже идущие переговоры.
# MESSAGE_MAX_NEW_THREADS_PER_DAY — анти-спам на массовые холодные рассылки
# новым людям (не ограничивает переписку в уже открытых тредах).
MESSAGE_MAX_LENGTH = 2000
MESSAGE_MAX_NEW_THREADS_PER_DAY = 20

# Вакансии (Фаза 4, 12.08.2026; переработано 26.08.2026 по ТЗ "Recruitment —
# ВАКАНСИИ" — раздел 0: минимализм, вакансия = 3 структурных поля + рейтинг
# + базовые условия, без обязательного текста). Публикует подписчик
# кабинета Рекрутер ИЛИ Компания (было — только рекрутер), просматривает
# любой с базовой подпиской GURO ID.
VACANCY_TITLE_MAX = 120
VACANCY_DESCRIPTION_MAX = 2000
VACANCY_LANGS = ("ru", "en")
VACANCY_STATUS_ACTIVE = "active"
VACANCY_STATUS_PAUSED = "paused"
VACANCY_STATUS_CLOSED = "closed"
VACANCY_LIST_LIMIT = 30

# Грейд вакансии — ТЕ ЖЕ 6 ключей, что в professions_data.PROFESSIONS
# (справочник должностей, раздел "Приложение" ТЗ) — Вертикаль→Грейд→
# Должность, единый источник и для анкеты регистрации, и для вакансий.
# "Инвестор" сюда намеренно не входит (см. ТЗ, раздел 3, п.3).
VACANCY_GRADES = ("C-Level", "Head of / Director", "Management", "Senior", "Specialist", "Junior / Entry")
# Сентинел последнего пункта каскадного списка должностей — открывает
# свободный ввод, значения логируются отдельно (см. guro_storage.
# log_vacancy_other_position) для последующего review справочника.
VACANCY_POSITION_OTHER = "Другое"

VACANCY_WORK_FORMATS = ("remote", "office", "hybrid")
VACANCY_EMPLOYMENT_TYPES = ("full", "part", "project")
# Контакт для отклика (раздел 3, п.11) — раньше был выбор "через GURO ID"
# либо внешняя ссылка (отклик тогда не создавал запись в системе, кандидат
# уходил вовне). 28.08.2026, фидбек владельца: вся коммуникация должна
# оставаться внутри приложения — вариант "внешняя ссылка" убран, остался
# единственный метод. VACANCY_CONTACT_METHODS — кортеж из одного значения,
# не голая константа: _parse_vacancy_fields в guro_id_api.py проверяет
# входящий contact_method через `in`, старые клиенты/данные с "external"
# автоматически откатываются на guro_id.
VACANCY_CONTACT_GURO_ID = "guro_id"
VACANCY_CONTACT_METHODS = (VACANCY_CONTACT_GURO_ID,)
VACANCY_DURATION_OPTIONS = (15, 30, 60)
VACANCY_DURATION_DEFAULT = 30

# Воронка статусов отклика — мини-ATS (раздел 5.3 ТЗ).
RESPONSE_STATUS_NEW = "new"
RESPONSE_STATUS_REVIEWING = "reviewing"
RESPONSE_STATUS_INTERVIEW = "interview"
RESPONSE_STATUS_OFFER = "offer"
RESPONSE_STATUS_HIRED = "hired"
RESPONSE_STATUS_REJECTED = "rejected"
RESPONSE_STATUSES = (
    RESPONSE_STATUS_NEW, RESPONSE_STATUS_REVIEWING, RESPONSE_STATUS_INTERVIEW,
    RESPONSE_STATUS_OFFER, RESPONSE_STATUS_HIRED, RESPONSE_STATUS_REJECTED,
)

# Расширение "Моё CV" (12.08.2026, по макету владельца "2Правки СV.pdf") —
# новые поля личного профиля, которых нет в анкете бота, редактируются
# прямо в Mini App (тот же принцип, что EXTRA_PROFILE_FIELDS). Гейтятся
# ОДНИМ уже существующим тумблером show_cv — не плодим новый тумблер под
# каждое поле, это всё один логический раздел "Моё CV".
CV_SIMPLE_FIELDS = ("cv_verticals", "cv_location", "cv_skills", "cv_languages", "cv_certifications")

# "Должность не более 2 раз в год" (владелец, 2Правки СV.pdf) — чтобы
# "сегодня менеджер, завтра директор" не подрывало доверие к CV. Считаем
# только РЕАЛЬНЫЕ изменения (не первое заполнение пустого поля), см.
# GuroStorage.set_cv_profession.
CV_PROFESSION_MAX_CHANGES_PER_YEAR = 2

# Ровно список грейдов из макета владельца — НЕ путать с constants.GRADES
# (та номенклатура для анкеты бота/вакансий, других сгенерированных полей,
# см. ТЗ) — тут воспроизведён буквально скриншот "Experience Level" из
# присланного макета, сознательно другой список.
CV_GRADE_LEVELS = (
    "Junior (0–2 years)", "Mid (2–5 years)", "Senior (5–8 years)",
    "Lead (8+ years)", "Head / Director", "C-Level / VP",
)

CV_EXPERIENCE_MAX = 20  # разумный потолок записей опыта работы на человека

# Привилегированные наблюдатели (12.08.2026, по прямой просьбе Павла —
# lizard_hoppers, user_id=1417059280 — и второго админа GuroArtem,
# user_id=8315845804): когда ОДИН ИЗ ЭТИХ ID выступает ЗАПРАШИВАЮЩИМ
# (requester) в поиске, для карточки ЦЕЛИ снимаются ОБЕ независимые оси
# сокрытия: (1) тумблеры приватности ЦЕЛИ (_apply_privacy) — видно всё,
# даже если владелец профиля не открыл НИ ОДНОГО show_*-тумблера;
# (2) «рейтинг сгорает без подписки» (_apply_subscription_gate, 12.08.2026
# расширено по отдельной явной просьбе "обойди и это тоже") — рейтинг/
# сделки ЦЕЛИ видны, даже если у самой цели сейчас нет активной подписки.
# НЕ влияет на приватность кабинета рекрутера (_apply_recruiter_privacy) —
# не запрашивалось, отдельная фича при необходимости. Список короткий и
# захардкожен намеренно — это ручная административная привилегия, не
# публичная функция продукта.
PRIVILEGED_VIEWER_IDS = (1417059280, 8315845804)
