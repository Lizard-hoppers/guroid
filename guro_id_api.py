"""GURO ID — отдельный веб-сервис (Mini App API + статика фронтенда).

Отдельный процесс от bot.py: только bot.py поллит getUpdates (два процесса на
один токен long-polling'ом конфликтуют), поэтому этот сервис лишь отдаёт JSON
и шлёт ПЕРВОЕ уведомление о партнёрстве через разовый `Bot(token=...)` — как
`taki_verify` у другого бота-соседа. Ответ на уведомление (кнопки Подтвердить/
Отклонить) и successful_payment обрабатывает уже основной бот
(handlers/guro_partnerships.py, handlers/guro_payments.py).

Слушает 127.0.0.1:GURO_ID_API_PORT, наружу — через nginx+TLS (см. OPERATIONS.md).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiohttp import web
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, WebAppInfo

import constants as C
import guro_chain_verify as GCV
import logic as MAIN_LOGIC
import guro_constants as GC
import community_access as CA
import guro_crypto as GCR
import guro_logic as GL
import guro_tags as GT
from config import Settings
from handlers.subscription_gate import release_gated_message
from guro_storage import GuroStorage
from professions_data import PROFESSIONS
from content import Content
from storage import Storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("guro_id_api")

WEBAPP_DIST = Path(__file__).resolve().parent / "webapp" / "dist"
# Загрузка лого/обложки компании (28.08.2026, фидбек владельца: "дай
# возможность загружать с галереи") — своя папка ВНЕ webapp/dist (тот
# перезаписывается при каждом npm run build + scp, файлы юзеров туда
# складывать нельзя), раздаётся отдельным static-роутом ниже.
COMPANY_UPLOADS_DIR = Path(__file__).resolve().parent / "webapp" / "uploads" / "company"
RECRUITER_UPLOADS_DIR = Path(__file__).resolve().parent / "webapp" / "uploads" / "recruiter"
# Сигнатуры форматов (без Pillow — его нет в venv, а тащить ради проверки
# 3 байт в начале файла избыточно) — не доверяем ни имени файла от клиента,
# ни его Content-Type, только реальным первым байтам.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"RIFF", "webp"),  # уточняется ниже (байты 8-11 == b"WEBP")
)
COMPANY_UPLOAD_MAX_BYTES = {"logo": 3 * 1024 * 1024, "cover": 5 * 1024 * 1024}


def _sniff_image_ext(data: bytes) -> str | None:
    for sig, ext in _IMAGE_SIGNATURES:
        if not data.startswith(sig):
            continue
        if ext == "webp" and data[8:12] != b"WEBP":
            continue
        return ext
    return None


# _BACKGROUND_TASKS (28.08.2026, багрепорт "долго грузится профиль") —
# держит ссылки на фоновые asyncio-таски, чтобы event loop не собрал их
# сборщиком мусора ДО завершения (стандартная ловушка fire-and-forget
# create_task без сохранённой ссылки — задача может оборваться посреди
# работы). См. _schedule_tag_sync ниже.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _schedule_tag_sync(settings: Settings, storage: GuroStorage, user_id: int, *, reason: str) -> None:
    """Обновление тега подписки в группе (см. guro_tags.py) — раньше
    ДОЖИДАЛИСЬ этого перед ответом /api/me, а это живой сетевой запрос к
    Telegram (создание нового Bot()-соединения + get_chat_member, иногда
    ещё и set_chat_member_tag) — на медленной сети до секунды на каждое
    открытие профиля. Тег не влияет на сам ответ /api/me (см. вызывающий
    код) — можно просто отправить в фон, не блокируя пользователя."""
    async def _run() -> None:
        try:
            await GT.sync_member_tag_standalone(
                settings.bot_token, settings.community_chat_id, storage, user_id, reason=reason,
            )
        except Exception:  # noqa: BLE001
            logger.exception("guro_id: tag sync failed for user %s", user_id)

    task = asyncio.create_task(_run())
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


FIRST_DAY_DISCOUNT_PCT = 20


def _first_day_discount_active(main_storage: Storage, user_id: int) -> bool:
    """Скидка -20% на МЕСЯЧНУЮ подписку GURO ID в день регистрации
    (11.09.2026, «Шаг 4. Подписка» дизайн-предложения, размер подтверждён
    владельцем). Завязана на profiles.created_at, а не отдельный флаг —
    сама перестаёт действовать назавтра, ничего не нужно сбрасывать.
    Работает одинаково для анкеты из бота и анкеты из приложения: обе
    пишут в одну таблицу profiles, различается только источник строки.
    Год скидку не получает — у него уже есть своя (-30%, stars_price_full).
    """
    profile = main_storage.get_profile_by_telegram_id(user_id)
    if profile is None:
        return False
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (profile["created_at"] or "")[:10] == today


def _auth(request: web.Request, settings: Settings) -> dict:
    """Достаёт и валидирует Telegram WebApp initData из заголовка
    `Authorization: tma <initData>` (или initData сырьём, для гибкости
    клиента). 401, если подписи нет/не сошлась/протухла."""
    header = request.headers.get("Authorization", "")
    init_data = header[4:].strip() if header[:4].lower() == "tma " else header.strip()
    user = GL.verify_init_data(init_data, settings.bot_token)
    if user is None:
        raise web.HTTPUnauthorized(reason="invalid_init_data")
    return user


def _profile_summary(storage: GuroStorage, user_id: int) -> dict | None:
    profile = storage.get_profile(user_id)
    if profile is None:
        return None
    guro_user = storage.get_or_create_guro_user(user_id)
    joined_at = profile["created_at"]
    joined_dt = GL.parse_db_datetime(joined_at)
    now = datetime.now(timezone.utc)
    days_in_community = (now - joined_dt).days if joined_dt else None

    # Счётчики оборота (ТЗ разделы 7-8) — публичные, но только по
    # подтверждённым ончейн суммам, см. turnover_stats.
    turnover = storage.turnover_stats(user_id)

    partners = []
    for p in storage.list_confirmed_partnerships(user_id):
        other_id = p["confirmer_id"] if p["initiator_id"] == user_id else p["initiator_id"]
        other_profile = storage.get_profile(other_id)
        amount_visible = bool(p["amount_visible"])
        # Оценка Шага 2 (6.1, 25.08.2026): своя — видна себе ВСЕГДА сразу
        # после отправки; чужая (про меня) — только после раскрытия
        # (rating_revealed_at), anti-retaliation (см. guro_storage._reveal_rating).
        my_rating_row = storage.get_my_rating(p["id"], user_id)
        other_rating_row = (
            storage.get_rating_of(p["id"], user_id) if p["rating_revealed_at"] else None
        )
        partners.append({
            "id": p["id"],
            "user_id": other_id,
            "username": other_profile["username"] if other_profile else None,
            "name": other_profile["name"] if other_profile else None,
            "confirmed_at": p["confirmed_at"],
            "counts_toward_rating": bool(p["counts_toward_rating"]),
            # Тип сделки (6, п.1, 25.08.2026) — Сделка/Найм, влияет на вес.
            "ptype": p["ptype"],
            # "Анонимная сделка" (11.09.2026) — сюда попадает всегда (в т.ч.
            # для СВОЕГО /api/me, участнику скрывать нечего), а вот у
            # ТРЕТЬИХ лиц имя/юзернейм/user_id по этому флагу обнулит
            # _scrub_anonymous_partners ниже (гейт применяется снаружи).
            "identity_visible": bool(p["identity_visible"]),
            # Офер/отзыв — публичны всегда (в этом и смысл "проверить
            # репутацию контакта", решение владельца 11.08.2026); суммы —
            # только если инициатор явно включил показ при создании заявки.
            "vertical": p["vertical"],
            "geo": p["geo"],
            "offer": p["offer"],
            "review": p["review"],
            "amount_received": p["amount_received"] if amount_visible else None,
            "amount_paid": p["amount_paid"] if amount_visible else None,
            # Хэш транзакции (16.08.2026) — та же видимость, что у суммы,
            # это подтверждение именно её, отдельного тумблера нет.
            "tx_hash": p["tx_hash"] if amount_visible else None,
            "tx_verified": bool(p["tx_verified"]) if amount_visible else None,
            # Три состояния проверки и сумма ИЗ транзакции (ТЗ разделы 2-3):
            # фронту нужно показать обе суммы рядом при расхождении.
            "tx_state": (p["tx_state"] or GC.TX_STATE_NONE) if amount_visible else None,
            "tx_amount": p["tx_amount"] if amount_visible else None,
            "tx_verify_error": p["tx_verify_error"] if amount_visible else None,
            "tx_network": p["tx_network"] if amount_visible else None,
            # Кто именно указал офер/суммы (со слов инициатора, не факт,
            # подтверждённый confirmer'ом) — фронту нужно, чтобы подписать
            # "получил/заплатил" с правильной стороны.
            "initiator_id": p["initiator_id"],
            # Оценка партнёрства, Шаг 2 (6.1, 25.08.2026).
            "my_rating": my_rating_row["verdict"] if my_rating_row else None,
            "other_rating": other_rating_row["verdict"] if other_rating_row else None,
            "other_rating_comment": other_rating_row["comment"] if other_rating_row else None,
            "rating_revealed": bool(p["rating_revealed_at"]),
        })

    extra = storage.get_extra_profile(user_id)
    cv_extra = storage.get_cv_extra(user_id)
    cv_experience = [dict(row) for row in storage.list_cv_experience(user_id)]
    return {
        "user_id": user_id,
        "username": profile["username"],
        "name": profile["name"],
        "company": profile["company"],
        "vertical": profile["vertical"],
        "profession": profile["profession"],
        # Своё значение из приложения, пока его нет — из анкеты бота
        # (тот же фолбэк, что у looking_for ниже).
        "turnover": turnover,
        "linkedin": extra["linkedin"] or profile["linkedin"],
        # "Что для вас сейчас актуально" из анкеты бота — семантически
        # ровно "Я ищу" из макета редизайна. 18.08.2026: сделано
        # редактируемым прямо в GURO ID (владелец просил после багрепорта
        # "не заполняется") — теперь это generic extra-поле guro_users
        # (EXTRA_PROFILE_FIELDS), с фолбэком на исходный ответ анкеты бота,
        # пока пользователь ни разу не отредактировал его в приложении.
        "looking_for": extra["looking_for"] or profile["request"],
        "cv_text": extra["cv_text"],
        "website": extra["website"],
        "offering": extra["offering"],
        # Расширение "Моё CV" (12.08.2026) — cv_profession/cv_grade/... и
        # список записей опыта работы, всё под одним тумблером show_cv.
        **cv_extra,
        "cv_experience": cv_experience,
        "work_status": guro_user["work_status"],
        "verified_screening": True,
        "joined_community_at": joined_at,
        "days_in_community": days_in_community,
        "reputation_score": round(guro_user["reputation_score"], 1),
        "reputation_tier": GL.reputation_tier(guro_user["reputation_score"]),
        "confirmed_partnerships": storage.count_confirmed_partnerships(user_id),
        "partners": partners,
        "subscription_status": guro_user["subscription_status"],
        "subscription_expires_at": guro_user["subscription_expires_at"],
        # Длина последнего оплаченного цикла (28.08.2026, макет "10 ·
        # Подписка") — для progress bar "осталось N дней" на фронте.
        "subscription_cycle_days": guro_user["subscription_cycle_days"],
        "is_subscribed": storage.is_subscribed(user_id),
        # Флаги для кнопок "Посмотреть как рекрутера"/"...компанию" в поиске
        # (SearchScreen.jsx). has_recruiter_profile обнаружен ОТСУТСТВУЮЩИМ
        # при работе над кабинетом "Компания" 16.08.2026 (комментарии в
        # коде описывали его как уже сделанный, по факту поля не было ни
        # тут, ни где-либо ещё в бэкенде — кнопка молча никогда не
        # показывалась) — заодно починил вместе с добавлением компании.
        "has_recruiter_profile": storage.is_recruiter_subscribed(user_id),
        "has_company_profile": storage.is_company_subscribed(user_id),
    }


# Поле профиля -> тумблер приватности, который его ПОКАЗЫВАЕТ. Opt-in для
# show_cv/show_contacts/show_offers (по умолчанию флаг выключен, поле
# скрыто, владелец сам включает) — но НЕ для show_name/show_company/
# show_vertical/show_profession, у тех default=1 (opt-out, см. ниже,
# 28.08.2026). Партнёрства (с кем сотрудничал) сюда намеренно не
# входят — тумблеры приватности их не трогают (это ядро смысла GURO ID),
# но их скрывает ДРУГОЙ, независимый механизм — подписка САМОГО владельца
# профиля, см. _apply_subscription_gate ниже.
#
# 25.08.2026 (фидбек владельца, "Правки.pdf", раздел "Мой рейтинг"):
# show_tenure/show_reputation убраны ИЗ ЭТОЙ КАРТЫ — "убрать приватность,
# рейтинг должен быть доступный (при условии, что человек оплатил
# подписку)". Значит рейтинг/стаж больше НЕ прячутся тумблером владельца —
# видимость определяет ТОЛЬКО подписка (уже существующая независимая ось,
# _apply_subscription_gate ниже, её не трогали). Сами колонки/тумблеры
# show_tenure/show_reputation в GC.PRIVACY_FIELDS/БД оставлены как есть
# (мёртвый, но безвредный остаток) — просто больше нигде не читаются,
# UI-тумблеры для них убраны (см. RatingSubscreen.jsx).
#
# 28.08.2026 (фидбек владельца, макет "01 · Профиль (личный)"): тумблеры
# show_name/show_company/show_vertical/show_profession были ненадолго
# убраны с ProfileHub.jsx и из этой карты — этот макет не показывал их
# вообще, поэтому они стали ВСЕГДА видны чужим (тот же принцип, что уже
# действует для username/партнёрств выше).
#
# 28.08.2026 (тот же день, макет "09 · Приватность", Untitled-12): следом
# нашёлся ОТДЕЛЬНЫЙ экран "Приватность профиля" (ProfileHub.jsx -> меню
# "Приватность" -> PrivacySubscreen.jsx) — с ровно этими же 4 тумблерами.
# Значит идея была не "убрать приватность совсем", а "убрать её С ГЛАВНОГО
# экрана, перенести на отдельный". Тумблеры возвращены в эту карту, но
# НЕ как opt-in (default=скрыто), а как opt-out (default=видно, см.
# guro_storage.py _init, _OPT_OUT_PRIVACY_FIELDS) — иначе каждый
# пользователь снова пропал бы из чужого поиска без своего ведома, пока
# сам не зайдёт в новый экран приватности. Прод-БД (где эти 4 колонки уже
# существовали с default=0) переведена на этот же opt-out одноразовой
# миграцией, см. migrate_privacy_opt_out_default.py.
_PRIVACY_FIELD_MAP = {
    "show_name": ("name",),
    "show_company": ("company",),
    "show_vertical": ("vertical",),
    "show_profession": ("profession",),
    "show_cv": ("cv_text", "cv_profession") + GC.CV_SIMPLE_FIELDS + (
        "cv_grade", "cv_relocation_ready", "cv_polygraph_consent",
        "cv_salary_from", "cv_salary_to", "cv_salary_negotiable", "cv_experience",
    ),
    "show_contacts": ("linkedin", "website"),
    "show_offers": ("looking_for", "offering"),
}


def _apply_privacy(summary: dict, privacy: dict, *, bypass: bool = False) -> dict:
    """Заменяет на None поля карточки ЧУЖОГО профиля, которые владелец НЕ
    включил в своих настройках (ключ остаётся — фронту проще проверять
    `=== null`, чем угадывать отсутствие ключа). Opt-in: поле видно, только
    если соответствующий тумблер явно включён. На собственный `/api/me` не
    вызывается — там нужен полный набор данных плюс сами настройки, см.
    handle_me. bypass=True (GC.PRIVILEGED_VIEWER_IDS, 12.08.2026) —
    административная привилегия конкретных запрашивающих: видят карточку
    целиком независимо от тумблеров ЦЕЛИ, ничего не редактируется."""
    if bypass:
        return dict(summary)
    result = dict(summary)
    for flag, fields in _PRIVACY_FIELD_MAP.items():
        if not privacy.get(flag):
            for field in fields:
                # cv_experience — список, скрытое состояние это [], не None
                # (тот же приём, что _apply_subscription_gate для partners).
                result[field] = [] if field == "cv_experience" else None
    return result


# «Рейтинг сгорает без подписки» (директива владельца, 10.08.2026): пока у
# владельца профиля НЕТ активной подписки — его репутация/сделки/наймы
# скрыты ото ВСЕХ, включая его самого. Сознательно РЕВЕРСИВНО — сами
# значения в БД не трогаем (reputation_score/партнёрства никуда физически
# не деваются), только прячем в выдаче API. Возобновил подписку — старое
# число мгновенно вернулось, ничего не потеряно. Отдельная ось от
# приватности (_apply_privacy) — та зависит от тумблеров смотрящего
# профиля, эта — от подписки владельца, применяется даже к его /api/me.
_SUBSCRIPTION_GATED_FIELDS = ("reputation_score", "reputation_tier", "confirmed_partnerships", "partners")


def _apply_subscription_gate(summary: dict, is_subscribed: bool, *, bypass: bool = False) -> dict:
    """bypass=True (GC.PRIVILEGED_VIEWER_IDS, 12.08.2026) — тот же админ-
    обход, что у _apply_privacy, но для ДРУГОЙ оси: показывает рейтинг/
    сделки ЦЕЛИ, даже если у неё самой сейчас нет активной подписки.
    Применяется ТОЛЬКО когда requester смотрит НА ЧУЖОЙ профиль
    (_profile_response/_scan_directory_candidates) — не в handle_me, там
    is_subscribed относится к САМОМУ запрашивающему, это другой смысл."""
    if is_subscribed or bypass:
        return summary
    result = dict(summary)
    for field in _SUBSCRIPTION_GATED_FIELDS:
        result[field] = None if field != "partners" else []
    return result


def _recruiter_tenure_days(row, now: datetime) -> int | None:
    activated = GL.parse_db_datetime(row["first_activated_at"])
    if activated is None:
        return None
    return max(0, (now - activated).days)


def _recruiter_summary(storage: GuroStorage, user_id: int) -> dict:
    """Кабинет рекрутера (Фаза 3, 12.08.2026) — САТЕЛЛИТ личного профиля,
    своя витрина + своя ОТДЕЛЬНАЯ подписка (рейтинг/партнёрства остаются
    общими, берутся из личного /api/me). is_recruiter_subscribed=False не
    404-ит (в отличие от NO_PROFILE у личного профиля) — фронт сам решает,
    показать апсейл или редактор, витрина технически "существует" с
    первого же запроса (get_or_create).

    26.08.2026 (ТЗ "Гуро рекрутер каб", главный экран) — добавлены: общий
    рейтинг (та же ось видимости, что у личного профиля — подписка
    ВЛАДЕЛЬЦА, см. _apply_subscription_gate), панель "Характеристика"
    (успешные наймы/активные вакансии/отклики-заглушка/стаж в роли),
    статус активности, кэш процентиля."""
    row = storage.get_or_create_recruiter_profile(user_id)
    extra = storage.get_recruiter_extra(user_id)
    guro_user = storage.get_or_create_guro_user(user_id)
    is_subscribed = storage.is_subscribed(user_id)
    percentile = storage.get_recruiter_percentile(user_id)
    return {
        "workspace": "recruiter",
        "user_id": user_id,
        **extra,
        "recruiter_subscription_status": row["subscription_status"],
        "recruiter_subscription_expires_at": row["subscription_expires_at"],
        "is_recruiter_subscribed": storage.is_recruiter_subscribed(user_id),
        # Общий рейтинг (не отдельный "рейтинг рекрутера" — раздел 3 ТЗ:
        # очки за найм идут в ОБЩИЙ W, тут просто тот же кружок, что и в
        # личном профиле). "Рейтинг сгорает без подписки" — та же ось.
        "reputation_score": round(guro_user["reputation_score"], 1) if is_subscribed else None,
        "reputation_tier": GL.reputation_tier(guro_user["reputation_score"]) if is_subscribed else None,
        # Панель "Характеристика" (2.3).
        "successful_hires": storage.count_confirmed_partnerships_by_type(user_id, GC.PARTNERSHIP_TYPE_HIRE),
        "active_vacancies": storage.count_active_vacancies(user_id, workspace="recruiter"),
        # "Откликов за 7 дней" (27.08.2026) — раньше был хардкод 0 (см. старый
        # комментарий: механики "Отклики" ещё не было), сама механика уже
        # реализована (guro_vacancy_responses), считаем реально.
        "responses_7d": storage.count_responses_since(
            user_id, datetime.now(timezone.utc) - timedelta(days=7), workspace="recruiter",
        ),
        # Оборот у кабинетов тот же, что в личном профиле: партнёрства и
        # рейтинг между ними общие (см. описание воркспейса выше), и два
        # разных ответа на «сколько у меня оборота» были бы враньём.
        "turnover": storage.turnover_stats(user_id),
        "tenure_days": _recruiter_tenure_days(row, datetime.now(timezone.utc)),
        # Статус активности (2.4) — отдельный от work_status личного профиля.
        "activity_status": row["activity_status"],
        # Блок процентиля (2.5) — только кэш, пересчитывается раз в сутки
        # (guro_recruiter_percentile_sync.py), см. GuroStorage.get_recruiter_percentile.
        "percentile_tier": percentile["tier"],
        "percentile_computed_at": percentile["computed_at"],
    }


def _company_summary(storage: GuroStorage, user_id: int) -> dict:
    """Кабинет "Компания" (16.08.2026) — зеркало _recruiter_summary выше,
    третий воркспейс поверх личного профиля.

    27.08.2026 (ТЗ "Роли и управление командой") — компания теперь МНОГИХ
    людей, не 1:1 с user_id: company_id резолвится через членство
    (get_company_membership), НЕ через сам user_id напрямую — иначе участник
    команды, никогда не создававший СВОЮ компанию, получил бы тут пустой
    новый профиль вместо той, в которой он состоит. no_company=True — юзер
    не Владелец и не Админ ни в одной компании (фронт предлагает создать
    свою ЛИБО подать заявку на присоединение к чужой).

    verified/verification_requested_at (26.08.2026, ТЗ "Компания. каб",
    раздел 2) — статус ручной верификации, НЕ влияет на видимость/
    функциональность, только на бейдж."""
    membership = storage.get_company_membership(user_id)
    if membership is None:
        return {"workspace": "company", "user_id": user_id, "no_company": True, "is_company_subscribed": False}
    company_id = membership["company_id"]
    row = storage.get_or_create_company_profile(company_id)
    extra = storage.get_company_extra(company_id)
    guro_user = storage.get_or_create_guro_user(user_id)
    is_subscribed = storage.is_subscribed(user_id)
    return {
        "workspace": "company",
        "user_id": user_id,
        "company_id": company_id,
        "my_role": membership["role"],
        "my_position": membership["position_text"],
        "member_count": storage.count_company_members(company_id),
        "member_limit": storage.company_member_limit(company_id),
        **extra,
        "company_subscription_status": row["subscription_status"],
        "company_subscription_expires_at": row["subscription_expires_at"],
        "is_company_subscribed": storage.is_company_subscribed(company_id),
        "verified": bool(row["verified"]),
        "verification_requested_at": row["verification_requested_at"],
        # Общий рейтинг — ЛИЧНЫЙ рейтинг СМОТРЯЩЕГО (см. докстринг выше:
        # "рейтинг сгорает без подписки" — это подписка САМОГО человека, не
        # компании), каждый участник качает СВОЙ личный профиль (раздел 0 ТЗ
        # "Роли и команда": "все получают баллы за сделки, прокачивают
        # личные профили") — карточка компании исторически показывала
        # рейтинг единственного владельца, теперь это рейтинг того, кто
        # сейчас смотрит на СВОЙ кабинет компании.
        "reputation_score": round(guro_user["reputation_score"], 1) if is_subscribed else None,
        "reputation_tier": GL.reputation_tier(guro_user["reputation_score"]) if is_subscribed else None,
        # Панель "Характеристика" (27.08.2026, ТЗ "экраны по ТЗ от 23.08",
        # "Кабинет «Компания»") — зеркало recruiter.characteristic, но
        # агрегировано на company_id: "успешных наймов" — сделки, подтверждённые
        # ЛЮБЫМ участником "от лица компании" (см. count_confirmed_
        # partnerships_by_type_for_company), "откликов за 7 дней" — по всем
        # вакансиям компании (см. count_responses_since).
        "successful_hires": storage.count_confirmed_partnerships_by_type_for_company(company_id, GC.PARTNERSHIP_TYPE_HIRE),
        "active_vacancies": storage.count_active_vacancies(company_id, workspace="company"),
        "responses_7d": storage.count_responses_since(
            user_id, datetime.now(timezone.utc) - timedelta(days=7), workspace="company",
        ),
        "turnover": storage.turnover_stats(user_id),
    }


async def handle_me(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)

    if request.query.get("workspace") == "recruiter":
        summary = _recruiter_summary(storage, user["id"])
        summary["privacy"] = storage.get_recruiter_privacy(user["id"])
        return web.json_response(summary)

    if request.query.get("workspace") == "company":
        summary = _company_summary(storage, user["id"])
        if not summary.get("no_company"):
            summary["privacy"] = storage.get_company_privacy(summary["company_id"])
        return web.json_response(summary)

    summary = _profile_summary(storage, user["id"])
    if summary is None:
        return web.json_response({"error": "NO_PROFILE"}, status=404)
    # Владелец в /api/me всегда видит СВОИ данные полностью — тумблеры влияют
    # только на то, что видят ЧУЖИЕ через /api/search (см. _apply_privacy).
    # Подписка — исключение: «рейтинг сгорает» без неё даже для себя самого.
    summary["privacy"] = storage.get_privacy(user["id"])
    summary = _apply_subscription_gate(summary, summary["is_subscribed"])
    summary["unread_messages"] = storage.count_unread_messages(user["id"])
    _schedule_tag_sync(settings, storage, user["id"], reason="api_me")
    return web.json_response(summary)


def _scrub_anonymous_partners(summary: dict, *, bypass: bool = False) -> dict:
    """"Анонимная сделка/найм" (11.09.2026) — третьим лицам (не самому
    участнику) не раскрываем, с кем была сделка: имя/юзернейм/user_id
    обнуляются для записей с identity_visible=False. user_id обнуляется
    ТОЖЕ, не только имя — иначе анонимность обходится подстановкой числа
    в /api/search?user_id=<leaked> (тот же вектор, которым мы уже закрывали
    утечку через username/name). bypass=True (GC.PRIVILEGED_VIEWER_IDS) —
    тот же админ-обход, что у _apply_privacy/_apply_subscription_gate: для
    разбора споров/фрода админу нужно видеть настоящих участников.
    Вызывается ТОЛЬКО когда смотрящий — не сам участник (см. _profile_
    response) — на собственный /api/me не влияет никогда."""
    if bypass:
        return summary
    partners = summary.get("partners")
    if not partners:
        return summary
    result = dict(summary)
    result["partners"] = [
        {**p, "user_id": None, "username": None, "name": None} if not p.get("identity_visible", True) else p
        for p in partners
    ]
    return result


def _profile_response(
    storage: GuroStorage, requester_id: int, target_profile, *, bypass_paywall: bool = False,
) -> dict:
    """Строит JSON для ОДНОГО профиля — полная карточка, если requester
    подписан, иначе урезанный бесплатный тизер (ТЗ экран 2). Общая логика
    для всех трёх режимов handle_search (user_id=/username=/точный матч
    внутри q=). bypass_paywall=True (18.08.2026, по запросу владельца
    после багрепорта "поделился CV — получатель увидел только тизер") —
    используется ТОЛЬКО для входа по user_id (QR-код/кнопка "Поделиться
    CV" — см. handle_search) — владелец явно решил, что сам факт перехода
    по личной ссылке = разрешение смотреть полностью, независимо от
    подписки СМОТРЯЩЕГО (как в LinkedIn). Свободный поиск по username=/q=
    остаётся платным как раньше — сюда не попадает."""
    privileged = requester_id in GC.PRIVILEGED_VIEWER_IDS
    summary = _profile_summary(storage, target_profile["user_id"])
    privacy = storage.get_privacy(target_profile["user_id"])
    summary = _apply_privacy(summary, privacy, bypass=privileged)
    # target'а (не смотрящего!) подписка гейтит рейтинг/сделки — «рейтинг
    # сгорает без подписки», см. _apply_subscription_gate.
    summary = _apply_subscription_gate(summary, summary["is_subscribed"], bypass=privileged)
    summary = _scrub_anonymous_partners(summary, bypass=privileged)

    if storage.is_subscribed(requester_id) or bypass_paywall:
        summary["locked"] = False
        summary["mode"] = "profile"
        return summary

    # Поля через .get() — приватность/subscription-гейт уже могли убрать
    # name/reputation_score выше. work_status — сознательное исключение из
    # пейволла (см. GC.WORK_STATUS_*): виден бесплатно, как маркер
    # "Open to Work", даже без подписки смотрящего.
    return {
        "mode": "profile",
        "user_id": summary["user_id"],
        "username": summary["username"],
        "name": summary.get("name"),
        "reputation_score": summary.get("reputation_score"),
        "confirmed_partnerships": summary["confirmed_partnerships"],
        "work_status": summary.get("work_status"),
        "locked": True,
    }


# Аналог _PRIVACY_FIELD_MAP для кабинета рекрутера (Фаза 3) — те же 9
# тумблеров (переиспользуем PRIVACY_FIELDS, отдельного набора не заводили),
# но show_tenure/show_reputation тут ни на что не влияют — стаж/рейтинг
# остаются свойством ЛИЧНОГО профиля, у витрины рекрутера их просто нет.
_RECRUITER_PRIVACY_FIELD_MAP = {
    # logo_url привязан к show_name (16.08.2026) — тот же тумблер, что и
    # имя/подпись, логотип без имени рядом смысла не несёт. Без этой
    # привязки поле утекало бы чужим ВСЕГДА, независимо от тумблеров —
    # RECRUITER_EXTRA_FIELDS добавляется в guro_constants.py как generic
    # список, а _apply_recruiter_privacy скрывает только то, что явно
    # перечислено в этой карте.
    "show_name": ("name", "logo_url"),
    "show_company": ("company",),
    "show_vertical": ("vertical",),
    "show_profession": ("profession",),
    "show_cv": ("cv_text",),
    "show_contacts": ("website",),
    "show_offers": ("offering",),
}


def _apply_recruiter_privacy(summary: dict, privacy: dict) -> dict:
    result = dict(summary)
    for flag, fields in _RECRUITER_PRIVACY_FIELD_MAP.items():
        if not privacy.get(flag):
            for field in fields:
                result[field] = None
    return result


def _recruiter_profile_response(storage: GuroStorage, requester_id: int, target_user_id: int) -> dict | None:
    """Карточка ЧУЖОГО кабинета рекрутера. None, если у цели нет активной
    подписки рекрутера — её витрины формально не существует для чужих,
    даже если запись в guro_recruiter_profiles уже создана (например, она
    успела открыть свой /api/me?workspace=recruiter один раз до оплаты)."""
    if not storage.is_recruiter_subscribed(target_user_id):
        return None
    extra = storage.get_recruiter_extra(target_user_id)
    privacy = storage.get_recruiter_privacy(target_user_id)
    summary = {"workspace": "recruiter", "mode": "profile", "user_id": target_user_id, **extra}
    summary = _apply_recruiter_privacy(summary, privacy)

    if storage.is_subscribed(requester_id):
        summary["locked"] = False
        return summary

    return {
        "workspace": "recruiter",
        "mode": "profile",
        "user_id": target_user_id,
        "name": summary.get("name"),
        "company": summary.get("company"),
        "locked": True,
    }


# Аналог _RECRUITER_PRIVACY_FIELD_MAP для кабинета "Компания" (16.08.2026) —
# те же PRIVACY_FIELDS, что и у рекрутера/личного профиля, но реально
# гейтят только 4 существующих поля (show_company/show_profession/
# show_offers/show_tenure/show_reputation тут ни на что не влияют — нет
# соответствующих полей у компании, тот же принцип "лишние тумблеры
# существуют, но неактивны", что уже принят у рекрутера).
_COMPANY_PRIVACY_FIELD_MAP = {
    "show_name": ("name", "logo_url"),
    "show_vertical": ("vertical",),
    "show_cv": ("description",),
    "show_contacts": ("website",),
}


def _apply_company_privacy(summary: dict, privacy: dict) -> dict:
    result = dict(summary)
    for flag, fields in _COMPANY_PRIVACY_FIELD_MAP.items():
        if not privacy.get(flag):
            for field in fields:
                result[field] = None
    return result


def _company_profile_response(storage: GuroStorage, requester_id: int, target_user_id: int) -> dict | None:
    """Карточка ЧУЖОГО кабинета "Компания" — зеркало _recruiter_profile_
    response выше. 27.08.2026 (ТЗ "Роли и команда") — target_user_id ищется
    как ЛЮБОЙ участник (Владелец или Админ) компании, не только основатель;
    is_member/can_join (раздел 3.1 ТЗ, кнопка "Запросить присоединение") —
    показывает requester_id, куда он смотрит относительно ЭТОЙ компании."""
    membership = storage.get_company_membership(target_user_id)
    if membership is None:
        return None
    company_id = membership["company_id"]
    if not storage.is_company_subscribed(company_id):
        return None
    extra = storage.get_company_extra(company_id)
    privacy = storage.get_company_privacy(company_id)
    requester_membership = storage.get_company_membership(requester_id)
    summary = {
        "workspace": "company", "mode": "profile", "user_id": target_user_id, "company_id": company_id,
        "verified": storage.is_company_verified(company_id), **extra,
        "is_member": requester_membership is not None and requester_membership["company_id"] == company_id,
        "can_join": requester_membership is None and requester_id != company_id,
    }
    summary = _apply_company_privacy(summary, privacy)

    if storage.is_subscribed(requester_id):
        summary["locked"] = False
        return summary

    return {
        "workspace": "company",
        "mode": "profile",
        "user_id": target_user_id,
        "company_id": company_id,
        "name": summary.get("name"),
        "verified": summary.get("verified"),
        "locked": True,
    }


# Поля, участвующие в directory-поиске по описанию (10.08.2026) — только
# "описательные" текстовые поля профиля. Осознанно НЕ включены: linkedin/
# website (это URL, не то, что ищут по смыслу), joined_community_at/
# days_in_community/reputation_score (числа/даты, не текст). Порядок не
# важен — просто склеиваются в один "поисковый слепок".
_DIRECTORY_TEXT_FIELDS = (
    "name", "company", "vertical", "profession", "cv_text", "looking_for", "offering",
    "cv_profession", "cv_skills", "cv_verticals", "cv_location",
)


def _searchable_text(summary: dict) -> str:
    return " ".join(str(summary.get(f) or "") for f in _DIRECTORY_TEXT_FIELDS).lower()


def _light_directory_summary(
    user_id: int, guro_row, profile_row, partnership_count: int, now: datetime,
) -> dict:
    """29.08.2026, аудит производительности — раньше directory-скан звал
    _profile_summary(storage, user_id) НА КАЖДОГО кандидата: это get_profile
    + get_or_create_guro_user + list_confirmed_partnerships (и для КАЖДОГО
    партнёрства ЕЩЁ get_profile контрагента + get_my_rating + get_rating_of)
    + get_extra_profile + get_cv_extra + list_cv_experience — при 65
    пользователях и почти пустой истории партнёрств уже сотни запросов на
    один поиск, а это синхронный код (блокирует event loop aiohttp целиком
    на время скана, не только для искателя).

    Ни _rank_directory_matches (итоговая карточка результата), ни
    _searchable_text/_grade_position_ok (сопоставление фильтрам), ни
    _apply_privacy/_apply_subscription_gate НЕ читают полный список
    партнёрств/оценок/опыта работы directory-кандидата — только его
    ПОДМНОЖЕСТВО полей (см. их код). Эта функция строит ТОЧНО такой же по
    ключам summary-словарь, каким его строит _profile_summary, но из уже
    оптом загруженных строк (guro_users/profiles одним SELECT на всех,
    счётчик партнёрств — одним GROUP BY на всех, см. bulk_* в
    guro_storage.py) — без единого похода в БД на кандидата. Поля,
    подтверждённо нигде не читаемые на этом пути (полный partners/
    cv_experience, linkedin/website и т.п. "паспортные" CV-поля вне
    _DIRECTORY_TEXT_FIELDS) — с безопасными дешёвыми заглушками
    (пустой список/None), а не настоящими значениями: их код только
    ОБНУЛЯЕТ по тумблеру приватности, никогда не выводит и не сравнивает.
    Полная, "тяжёлая" карточка ОДНОГO профиля (открыл конкретную анкету)
    по-прежнему идёт через _profile_summary — этот путь не менялся."""
    looking_for = guro_row["looking_for"] or profile_row["request"]
    is_subscribed = GL.subscription_active(
        guro_row["subscription_status"], GL.parse_db_datetime(guro_row["subscription_expires_at"]), now,
    )
    return {
        "user_id": user_id,
        "username": profile_row["username"],
        "name": profile_row["name"],
        "company": profile_row["company"],
        "vertical": profile_row["vertical"],
        "profession": profile_row["profession"],
        "looking_for": looking_for,
        "cv_text": guro_row["cv_text"],
        "offering": guro_row["offering"],
        "cv_profession": guro_row["cv_profession"],
        "cv_skills": guro_row["cv_skills"],
        "cv_verticals": guro_row["cv_verticals"],
        "cv_location": guro_row["cv_location"],
        "work_status": guro_row["work_status"],
        "reputation_score": round(guro_row["reputation_score"], 1),
        "reputation_tier": GL.reputation_tier(guro_row["reputation_score"]),
        "confirmed_partnerships": partnership_count,
        "partners": [],  # см. докстринг — не читается на этом пути
        "cv_experience": [],  # см. докстринг — не читается на этом пути
        "is_subscribed": is_subscribed,
    }


def _scan_directory_candidates(
    storage: GuroStorage, requester_id: int, match_fn, *, require_privacy_open: bool = True,
) -> list[tuple[int, dict]]:
    """Общий проход по всем GURO ID пользователям для всех directory-режимов
    (поиск по описанию, browse по вертикали, резюме — Фазы 2/4) — экономит
    поход в БД для тех, кто вообще ничего не открыл тумблерами приватности.
    match_fn(summary) -> int > 0, чтобы попасть в выдачу (сила совпадения,
    используется для сортировки), иначе кандидат исключается.
    require_privacy_open=False (резюме, Фаза 4) — work_status виден ВСЕГДА
    независимо от тумблеров (тот же принцип, что и в остальном приложении),
    поэтому для поиска "кто ищет работу" пропускать людей без единого
    открытого поля было бы неверно — их сигнал "ищу работу" всё равно
    публичный. Привилегированный requester (GC.PRIVILEGED_VIEWER_IDS,
    12.08.2026) видит ВСЕХ независимо от require_privacy_open — иначе
    админ-обход приватности не работал бы в directory-поиске/browse, только
    в точном поиске по юзернейму.

    29.08.2026 — данные теперь оптом (3 запроса на весь скан, не 10-20 на
    кандидата), см. _light_directory_summary."""
    bypass = requester_id in GC.PRIVILEGED_VIEWER_IDS
    now = datetime.now(timezone.utc)
    guro_users_by_id = storage.bulk_guro_users_by_id()
    profiles_by_id = storage.bulk_latest_profiles_by_id()
    partnership_counts = storage.bulk_confirmed_partnership_counts()
    matches: list[tuple[int, dict]] = []
    for user_id in storage.list_guro_user_ids():
        if user_id == requester_id:
            continue  # сам себя в directory-режимах видеть незачем
        guro_row = guro_users_by_id.get(user_id)
        profile_row = profiles_by_id.get(user_id)
        if guro_row is None or profile_row is None:
            continue  # тот же случай, что _profile_summary is None раньше
        privacy = {field: bool(guro_row[field]) for field in GC.PRIVACY_FIELDS}
        if require_privacy_open and not bypass and not any(privacy.values()):
            continue  # ничего не открыто -> нечего показывать
        summary = _light_directory_summary(
            user_id, guro_row, profile_row, partnership_counts.get(user_id, 0), now,
        )
        summary = _apply_privacy(summary, privacy, bypass=bypass)
        summary = _apply_subscription_gate(summary, summary["is_subscribed"], bypass=bypass)
        score = match_fn(summary)
        if score > 0:
            matches.append((score, summary))
    return matches


def _rank_directory_matches(matches: list[tuple[int, dict]], *, top: bool) -> dict:
    """top=True («ТОП рейтинга», 11.08.2026) — чистая сортировка по
    репутации вместо силы совпадения (для browse по вертикали сила
    совпадения всегда одинакова, там top лишь один осмысленный порядок).

    28.08.2026 (макет "10 · Подписка", Untitled-13) — экран подписки прямо
    обещает "Приоритет в выдаче при равном рейтинге", а сортировка этого
    не делала вообще (только совпадение + репутация, при точном равенстве
    порядок был случайным побочным эффектом стабильной сортировки по
    list_guro_user_ids()). is_subscribed добавлен последним ключом
    сортировки — тай-брейк, не основной критерий."""
    if top:
        ranked = sorted(
            matches,
            key=lambda pair: (pair[1].get("reputation_score") or 0, bool(pair[1].get("is_subscribed"))),
            reverse=True,
        )
    else:
        ranked = sorted(
            matches,
            key=lambda pair: (pair[0], pair[1].get("reputation_score") or 0, bool(pair[1].get("is_subscribed"))),
            reverse=True,
        )
    sliced = ranked[: GC.DIRECTORY_RESULTS_LIMIT]
    results = [
        {
            "user_id": s["user_id"],
            "username": s["username"],
            "name": s.get("name"),
            "vertical": s.get("vertical"),
            "profession": s.get("profession"),
            "company": s.get("company"),
            "work_status": s.get("work_status"),
            "reputation_score": s.get("reputation_score"),
            "confirmed_partnerships": s.get("confirmed_partnerships"),
        }
        for _, s in sliced
    ]
    return {"mode": "list", "results": results, "truncated": len(ranked) > len(sliced)}


def _directory_search(
    storage: GuroStorage, requester_id: int, query: str, *, top: bool,
    vertical: str | None = None, grade: str | None = None,
    position: str | None = None, looking: bool = False,
) -> dict:
    """Поиск ПО ОПИСАНИЮ ("менеджер в крипто") — список всех, у кого есть
    совпадение среди полей, которые они САМИ открыли тумблерами
    приватности. Вызывается из handle_search, когда q= не совпал ни с
    одним точным юзернеймом (см. режимы ниже) — доступ уже проверен
    вызывающим (платная фича, 402 без подписки).

    06.09.2026: принимает те же фильтры, что и _directory_browse. Раньше
    текст и чипы были взаимоисключающими, и рекрутер, выбравший Gambling и
    написавший «Team Lead», получал совпадения по всем вертикалям сразу."""
    keywords = query.lower().split()[: GC.DIRECTORY_QUERY_MAX_KEYWORDS]
    vertical_lower = (vertical or "").strip().lower()
    grade_lower = (grade or "").strip().lower()
    position_lower = (position or "").strip().lower()

    def match_fn(summary: dict) -> int:
        if looking and summary.get("work_status") != GC.WORK_STATUS_LOOKING:
            return 0
        if vertical_lower:
            v = (summary.get("vertical") or "").lower()
            if v != vertical_lower and not (vertical_lower == "other" and v.startswith("other")):
                return 0
        if not _grade_position_ok(summary, grade_lower, position_lower):
            return 0
        haystack = _searchable_text(summary)
        return sum(1 for kw in keywords if kw in haystack)

    matches = _scan_directory_candidates(
        storage, requester_id, match_fn, require_privacy_open=not looking,
    )
    return _rank_directory_matches(matches, top=top)


def _grade_position_ok(summary: dict, grade_lower: str, position_lower: str) -> bool:
    """Грейд/должность (27.08.2026, ТЗ "экраны по ТЗ от 23.08", "Поиск
    кандидатов") — у личного профиля нет структурированной таксономии грейда
    вакансий (cv_grade использует ДРУГОЙ список меток, см. CV_GRADE_LEVELS в
    guro_constants.py — это сознательно другой справочник, "Experience Level"
    из макета CV, не C-Level/Head of Director/... вакансий), поэтому матчим
    подстрокой по тем же полям, что _directory_search (_searchable_text)."""
    if not grade_lower and not position_lower:
        return True
    haystack = _searchable_text(summary)
    if grade_lower and grade_lower not in haystack:
        return False
    if position_lower and position_lower not in haystack:
        return False
    return True


def _directory_browse(
    storage: GuroStorage, requester_id: int, vertical: str, *,
    grade: str | None = None, position: str | None = None, top: bool,
) -> dict:
    """Browse по вертикали (11.08.2026) — альтернатива текстовому поиску
    для тех, кто не знает точного юзернейма и не хочет формулировать
    запрос (см. PDF-фидбек владельца: "пока не понятно как они будут
    находить друг друга"). Сравнение — с КАНОНИЧЕСКИМ значением из
    constants.VERTICALS (то, что реально пишется в profiles.vertical при
    регистрации, см. handlers/flow.py), "Other" дополнительно матчит
    произвольные "Other: <текст>". grade/position — необязательные
    доп. фильтры кабинета Рекрутер/Компания (см. _grade_position_ok),
    личный профиль (SearchScreen.jsx) их не передаёт."""
    vertical_lower = vertical.strip().lower()
    grade_lower = (grade or "").strip().lower()
    position_lower = (position or "").strip().lower()

    def match_fn(summary: dict) -> int:
        if vertical_lower:
            v = (summary.get("vertical") or "").lower()
            if v != vertical_lower and not (vertical_lower == "other" and v.startswith("other")):
                return 0
        return 1 if _grade_position_ok(summary, grade_lower, position_lower) else 0

    matches = _scan_directory_candidates(storage, requester_id, match_fn)
    return _rank_directory_matches(matches, top=top)


def _resume_browse(
    storage: GuroStorage, requester_id: int, vertical: str | None, *,
    grade: str | None = None, position: str | None = None, top: bool,
) -> dict:
    """«Резюме» (Фаза 4, 12.08.2026) — не отдельный экран/эндпоинт, а
    доп. фильтр к тому же поиску: показывает только тех, кто отметил
    статус «Ищу работу» (work_status=looking), опционально ещё и по
    вертикали/грейду/должности (27.08.2026, см. _grade_position_ok).
    require_privacy_open=False — см. _scan_directory_candidates."""
    vertical_lower = (vertical or "").strip().lower()
    grade_lower = (grade or "").strip().lower()
    position_lower = (position or "").strip().lower()

    def match_fn(summary: dict) -> int:
        if summary.get("work_status") != GC.WORK_STATUS_LOOKING:
            return 0
        if vertical_lower:
            v = (summary.get("vertical") or "").lower()
            if v != vertical_lower and not (vertical_lower == "other" and v.startswith("other")):
                return 0
        return 1 if _grade_position_ok(summary, grade_lower, position_lower) else 0

    matches = _scan_directory_candidates(storage, requester_id, match_fn, require_privacy_open=False)
    return _rank_directory_matches(matches, top=top)


async def handle_candidates_count(request: web.Request) -> web.Response:
    """Живой счётчик "Показать N кандидатов" (28.08.2026, макет "12 ·
    Рекрутер — Поиск кандидатов") — та же фильтрация, что и _directory_
    browse/_resume_browse (vertical/grade/position/looking), но без
    ранжирования и без сборки полных карточек, только count. Гейт
    подписки тот же (any_subscription_active) — иначе можно было бы
    бесплатно узнавать размер выдачи, не оплачивая сам поиск."""
    settings, storage = request.app["settings"], request.app["storage"]
    requester = _auth(request, settings)
    if storage.is_frozen(requester["id"]):
        return web.json_response({"error": "ACCOUNT_FROZEN"}, status=403)
    if not storage.any_subscription_active(requester["id"]):
        return web.json_response({"error": "SUBSCRIPTION_REQUIRED"}, status=402)

    vertical_lower = request.query.get("vertical", "").strip().lower()
    grade_lower = request.query.get("grade", "").strip().lower()
    position_lower = request.query.get("position", "").strip().lower()
    looking = request.query.get("resumes") == "1"

    def match_fn(summary: dict) -> int:
        if looking and summary.get("work_status") != GC.WORK_STATUS_LOOKING:
            return 0
        if vertical_lower:
            v = (summary.get("vertical") or "").lower()
            if v != vertical_lower and not (vertical_lower == "other" and v.startswith("other")):
                return 0
        return 1 if _grade_position_ok(summary, grade_lower, position_lower) else 0

    matches = _scan_directory_candidates(storage, requester["id"], match_fn, require_privacy_open=not looking)
    return web.json_response({"count": len(matches)})


async def handle_search(request: web.Request) -> web.Response:
    """Режимы запроса:
    - `user_id=<id>` — точный переход по ID (QR, клик по результату поиска).
    - `username=<name>` — точный переход по юзернейму (внутреннее использование).
    - `vertical=<v>` — browse по вертикали (11.08.2026, см. _directory_browse),
      платный, как и q=-описание.
    - `resumes=1` (Фаза 4, 12.08.2026) — «резюме»: только work_status=looking,
      можно сочетать с `vertical=` для сужения. Платный (см. _resume_browse).
    - `q=<текст>` — УНИВЕРСАЛЬНЫЙ поиск (10.08.2026, единственный режим,
      доступный из формы поиска фронта): сперва пробуем точный юзернейм
      (бесплатный тизер, как раньше) — не нашли, значит это уже описание,
      платный directory-поиск по открытым полям (см. _directory_search).
    `top=1` (любой из платных режимов) — сортировка «ТОП рейтинга» вместо
    силы совпадения, см. _rank_directory_matches."""
    settings, storage = request.app["settings"], request.app["storage"]
    requester = _auth(request, settings)
    # Антифрод (ТЗ 7.3, 25.08.2026) — заморозка блокирует именно поиск/
    # просмотр (сам механизм абьюза), не всё API (сообщения/CV и т.п.).
    if storage.is_frozen(requester["id"]):
        return web.json_response({"error": "ACCOUNT_FROZEN"}, status=403)
    username = request.query.get("username", "")
    user_id_param = request.query.get("user_id", "")
    query = request.query.get("q", "")
    vertical = request.query.get("vertical", "").strip()
    top = request.query.get("top") == "1"
    resumes = request.query.get("resumes") == "1"
    # grade/position (27.08.2026, "Поиск кандидатов" — см. _grade_position_ok)
    # — доп. фильтры, личный профиль их не отправляет, поведение не меняется.
    grade = request.query.get("grade", "").strip()
    position = request.query.get("position", "").strip()

    if request.query.get("workspace") == "recruiter":
        # Просмотр ЧУЖОГО кабинета рекрутера (Фаза 3) — резолвим человека
        # ровно так же, как в личном режиме (по id/юзернейму/q=), но
        # отдаём recruiter-карточку вместо обычной. Витрины разработчика
        # и directory-режимов (vertical=/описание) у рекрутера нет —
        # только точный переход на конкретного человека.
        target_id: int | None = None
        if user_id_param:
            try:
                target_id = int(user_id_param)
            except ValueError:
                target_id = None
        elif username:
            target_profile = storage.find_profile_by_username(username)
            target_id = target_profile["user_id"] if target_profile else None
        else:
            q = query.strip()
            target_profile = storage.find_profile_by_username(q) if q else None
            target_id = target_profile["user_id"] if target_profile else None
        if target_id is None:
            return web.json_response({"error": "NOT_FOUND"}, status=404)
        response = _recruiter_profile_response(storage, requester["id"], target_id)
        if response is None:
            return web.json_response({"error": "NO_RECRUITER_PROFILE"}, status=404)
        return web.json_response(response)

    if request.query.get("workspace") == "company":
        # Просмотр ЧУЖОГО кабинета "Компания" (16.08.2026) — зеркало ветки
        # workspace=recruiter выше.
        target_id: int | None = None
        if user_id_param:
            try:
                target_id = int(user_id_param)
            except ValueError:
                target_id = None
        elif username:
            target_profile = storage.find_profile_by_username(username)
            target_id = target_profile["user_id"] if target_profile else None
        else:
            q = query.strip()
            target_profile = storage.find_profile_by_username(q) if q else None
            target_id = target_profile["user_id"] if target_profile else None
        if target_id is None:
            return web.json_response({"error": "NOT_FOUND"}, status=404)
        response = _company_profile_response(storage, requester["id"], target_id)
        if response is None:
            return web.json_response({"error": "NO_COMPANY_PROFILE"}, status=404)
        return web.json_response(response)

    if user_id_param:
        # Заход по QR/"Поделиться CV" (?target=<id> у Mini App, см.
        # App.jsx) — ищем по ID, не по юзернейму (тот мог смениться, ID
        # стабилен). bypass_paywall=True: переход по личной ссылке
        # открывает профиль полностью независимо от подписки смотрящего
        # (18.08.2026, см. _profile_response) — единственный путь сюда это
        # QR/расшаренная ссылка/клик по уже открытой карточке из платного
        # поиска (тогда requester и так уже подписан, флаг ничего не меняет).
        try:
            target_profile = storage.get_profile(int(user_id_param))
        except ValueError:
            target_profile = None
        if target_profile is None:
            return web.json_response({"error": "NOT_FOUND"}, status=404)
        if not _check_profile_view_limit(storage, requester["id"], target_profile["user_id"]):
            return web.json_response({"error": "VIEW_LIMIT_REACHED", "resets_at": _next_utc_midnight_iso()}, status=429)
        return web.json_response(
            _profile_response(storage, requester["id"], target_profile, bypass_paywall=True)
        )

    if username:
        target_profile = storage.find_profile_by_username(username)
        if target_profile is None:
            return web.json_response({"error": "NOT_FOUND"}, status=404)
        if not _check_profile_view_limit(storage, requester["id"], target_profile["user_id"]):
            return web.json_response({"error": "VIEW_LIMIT_REACHED", "resets_at": _next_utc_midnight_iso()}, status=429)
        return web.json_response(_profile_response(storage, requester["id"], target_profile))

    # «Поиск кандидатов» кабинета Рекрутер/Компания (06.09.2026,
    # «рекрутер полный.pdf», стр. 3-5). Своя область со своими правилами —
    # личный профиль сюда не попадает и остаётся на точном юзернейме, как
    # решено 25.08.2026.
    if request.query.get("scope") == "candidates":
        if not storage.any_subscription_active(requester["id"]):
            return web.json_response({"error": "SUBSCRIPTION_REQUIRED"}, status=402)
        q = query.strip()
        if q:
            # Точный юзернейм — самый дешёвый и частый случай, пробуем его
            # первым. Не совпало — значит это описание, а не адрес.
            target_profile = storage.find_profile_by_username(q)
            if target_profile is not None:
                if not _check_profile_view_limit(storage, requester["id"], target_profile["user_id"]):
                    return web.json_response(
                        {"error": "VIEW_LIMIT_REACHED", "resets_at": _next_utc_midnight_iso()}, status=429,
                    )
                return web.json_response(_profile_response(storage, requester["id"], target_profile))
            return web.json_response(_directory_search(
                storage, requester["id"], q, top=top,
                vertical=vertical or None, grade=grade or None,
                position=position or None, looking=resumes,
            ))
        # Пустой запрос — это НЕ «ничего не искали», а «показать всех, кого
        # обещал счётчик». Раньше здесь возвращался пустой список, и кнопка
        # «Показать 59 кандидатов» показывала ноль.
        if resumes:
            return web.json_response(_resume_browse(
                storage, requester["id"], vertical or None,
                grade=grade or None, position=position or None, top=top,
            ))
        return web.json_response(_directory_browse(
            storage, requester["id"], vertical,
            grade=grade or None, position=position or None, top=top,
        ))

    # any_subscription_active (26.08.2026, ТЗ "Гуро рекрутер каб", "Найти
    # кандидата") — рекрутер/компания тоже могут просматривать резюме/
    # вертикали, не обязательно имея ЛИЧНУЮ подписку GURO ID отдельно.
    if resumes:
        if not storage.any_subscription_active(requester["id"]):
            return web.json_response({"error": "SUBSCRIPTION_REQUIRED"}, status=402)
        return web.json_response(
            _resume_browse(storage, requester["id"], vertical or None, grade=grade or None, position=position or None, top=top)
        )

    if vertical or grade or position:
        if not storage.any_subscription_active(requester["id"]):
            return web.json_response({"error": "SUBSCRIPTION_REQUIRED"}, status=402)
        return web.json_response(
            _directory_browse(storage, requester["id"], vertical, grade=grade or None, position=position or None, top=top)
        )

    q = query.strip()
    if not q:
        return web.json_response({"mode": "list", "results": [], "truncated": False})

    target_profile = storage.find_profile_by_username(q)
    if target_profile is not None:
        if not _check_profile_view_limit(storage, requester["id"], target_profile["user_id"]):
            return web.json_response({"error": "VIEW_LIMIT_REACHED", "resets_at": _next_utc_midnight_iso()}, status=429)
        return web.json_response(_profile_response(storage, requester["id"], target_profile))

    # 25.08.2026 (фидбек владельца, "Правки.pdf", раздел "Поиск"): поиск по
    # описанию (`_directory_search`, ниже) убран из ЛИЧНОГО профиля — там
    # отныне ТОЛЬКО точный юзернейм. Логика: описание/параметры/резюме —
    # это функционал кабинетов Рекрутер/Компания (там за это отдельная
    # подписка), личный профиль — только предъявить/проверить себя по
    # юзернейму. Функция `_directory_search` НЕ удалена — понадобится,
    # когда описание-поиск будет добавлено в workspace=recruiter/company
    # (не в этом раунде, отдельная будущая задача).
    return web.json_response({"error": "NOT_FOUND"}, status=404)


async def _notify_confirmer(bot_token: str, confirmer_id: int, initiator_username: str, partnership_id: int) -> None:
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Подтвердить", callback_data=f"guro:confirm:{partnership_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"guro:decline:{partnership_id}"),
    ]])
    bot = Bot(token=bot_token)
    async with bot:
        await bot.send_message(
            confirmer_id,
            f"🤝 @{initiator_username} отметил(а) через GURO ID сотрудничество с вами. Подтвердить?",
            reply_markup=kb,
        )


def _body_text(body: dict, key: str, default: str = "") -> str:
    """Текстовое поле из тела запроса, где null означает «пусто».

    str(body.get(key, "")) для этого не годится: второй аргумент .get()
    срабатывает, только когда ключа НЕТ, а фронт штатно присылает ключ со
    значением null — и str(None) даёт строку "None" длиной четыре символа.
    Дальше она ведёт себя как заполненное значение: включает проверки «поле
    задано» и попадает в базу вместо пустоты (06.09.2026, «компания.pdf»,
    стр. 6; ровно так в боевой базе оказался хеш 'None')."""
    value = body.get(key, default)
    return default if value is None else str(value)


def _parse_amount(raw) -> float | None:
    """Пустая строка/None/мусор -> None (сумма не указана), а не 400 —
    поле необязательное."""
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


async def handle_create_partnership(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    confirmer_username = str(body.get("confirmer_username", "")).strip()
    vertical = body.get("vertical") or None
    geo = body.get("geo") or None
    offer = (_body_text(body, "offer").strip()[:300]) or None
    # Свободный "отзыв" убран с этого шага (25.08.2026, фидбек владельца
    # "Правки.pdf": факт сотрудничества и оценка/отзыв — теперь два разных
    # шага, см. submit_rating/6.1) — старые записи с review сохраняются и
    # по-прежнему отображаются (PartnerRow), просто новых больше не будет.
    review = None
    amount_received = _parse_amount(body.get("amount_received"))
    amount_paid = _parse_amount(body.get("amount_paid"))
    amount_visible = bool(body.get("amount_visible"))
    # Хэш транзакции (16.08.2026) — 200 симв. с запасом покрывает любые
    # реальные хэши (Bitcoin/Ethereum/TRON и т.д. — все короче 100).
    # 25.08.2026: юзеру проще прислать ссылку на транзакцию целиком, чем
    # копировать голый хэш (фидбек владельца) — extract_tx_hash вырезает
    # хэш из известных explorer-ссылок (Tronscan/Etherscan/BscScan), иначе
    # оставляет ввод как есть (уже голый хэш).
    raw_tx_input = _body_text(body, "tx_hash")
    # Нормализованный вид (ТЗ «Hash_Uniqueness», раздел 2) — и хранится, и
    # сравнивается только он.
    tx_hash = GCV.normalize_tx_hash(raw_tx_input)[:200] or None
    # Тип партнёрства (6, п.1, 25.08.2026) — обязательный, влияет на
    # базовый вес (5.1). Сеть (6, п.2) обязательна, ТОЛЬКО если указан хэш —
    # без неё нельзя понять, какой explorer API дёргать (ETH/BSC неотличимы
    # по формату хэша, см. guro_chain_verify.py).
    ptype = str(body.get("ptype", "")).strip()
    tx_network = _body_text(body, "tx_network").strip() or None
    # Сеть из ссылки на эксплорер (ТЗ раздел 5): если вставили ссылку,
    # выбирать сеть руками незачем — она уже в домене.
    if tx_hash and not tx_network:
        tx_network = GCV.detect_network(raw_tx_input)
    is_flagged_fraud = bool(body.get("is_flagged_fraud"))
    # "Анонимная сделка/найм" (11.09.2026) — инициатор решает в момент
    # создания заявки, как и amount_visible; распространяется на ОБЕИХ
    # участников симметрично (см. _scrub_anonymous_partners).
    identity_visible = not bool(body.get("anonymous"))
    # Код отказа пишем в лог: в access-логе виден только статус, и по нему
    # причину не восстановить (05.09.2026 — пришлось вычислять её по длине
    # ответа, что ненадёжно).
    def _reject(code: str, status: int, **extra):
        logger.warning(
            "guro_id: заявка на партнёрство отклонена: %s (user=%s, ptype=%r, network=%r, hash=%s)",
            code, user["id"], ptype, tx_network, "есть" if tx_hash else "нет",
        )
        return web.json_response({"error": code, **extra}, status=status)

    if ptype not in GC.PARTNERSHIP_TYPES:
        return _reject("INVALID_TYPE", 400)
    if tx_hash and tx_network not in GC.TX_NETWORKS:
        return _reject("INVALID_NETWORK", 400)
    # Денежная сделка без хеша больше не заводится («рекрутер каб.pdf»,
    # стр. 4 и 6). Признак безоплатного партнёрства — отсутствие суммы:
    # форма при отмеченном чекбоксе присылает обе суммы пустыми, и
    # требовать хеш там не с чего.
    if (amount_received or amount_paid) and not tx_hash:
        return _reject("TX_HASH_REQUIRED", 400)

    # Один хеш = одно партнёрство (ТЗ «Hash_Uniqueness», разделы 1-3).
    # Проверяем ДО создания записи, на шаге 1, а не после подтверждения
    # контрагентом. Текст отказа зависит от того, кто спрашивает.
    if tx_hash:
        taken = storage.find_partnership_by_tx_hash(tx_hash)
        if taken is not None:
            own = user["id"] in (taken["initiator_id"], taken["confirmer_id"])
            if own:
                # Чаще всего это не накрутка, а непонимание: сделка уже
                # зафиксирована с двух сторон, и человек заводит её второй
                # раз. Показываем, с кем и когда, — этих данных он и так
                # не лишён, партнёрство его собственное.
                other_id = (
                    taken["confirmer_id"] if taken["initiator_id"] == user["id"]
                    else taken["initiator_id"]
                )
                other = storage.get_profile(other_id)
                return _reject(
                    "TX_HASH_USED_BY_OWN", 409,
                    partner_username=(other["username"] if other else None),
                    partnership_date=taken["created_at"],
                )
            # Чужая сделка: детали не раскрываем — это приватные данные
            # третьих лиц (ТЗ раздел 3, случай B).
            return _reject("TX_HASH_ALREADY_USED", 409)

    # as_company (27.08.2026, ТЗ "Роли и команда", раздел 6) — "действую как
    # <бренд>": сделка попадает в общую историю компании, лимит новых заявок
    # (раздел 2.2 ТЗ "Тарифы и лимиты", "30 на аккаунт компании в целом")
    # считается на компанию, а не персонально на участника.
    company_id = None
    if body.get("as_company"):
        membership = storage.get_company_membership(user["id"])
        if membership is None or not storage.is_company_subscribed(membership["company_id"]):
            return _reject("COMPANY_SUBSCRIPTION_REQUIRED", 402)
        company_id = membership["company_id"]

    # Раздел 2.2 ТЗ "Тарифы и лимиты" — лимит НОВЫХ заявок/день (не путать с
    # RATE_LIMIT_HOURS в create_partnership — тот про повтор ОДНОЙ пары).
    if company_id is not None:
        daily_limit = storage.get_effective_limit(
            company_id, GC.LIMIT_KEY_REQUESTS_COMPANY, GC.LIMIT_NEW_REQUESTS_PER_DAY_COMPANY,
        )
        today_count = storage.count_new_company_partnerships_today(company_id)
    else:
        daily_limit = _new_requests_per_day_limit(storage, user["id"])
        today_count = storage.count_new_partnerships_today(user["id"])
    if today_count >= daily_limit:
        return _reject("DAILY_REQUEST_LIMIT_REACHED", 429, resets_at=_next_utc_midnight_iso())

    target_profile = storage.find_profile_by_username(confirmer_username)
    if target_profile is None:
        return _reject("NO_CONFIRMER_PROFILE", 404)

    # Ончейн-проверка (ТЗ «Верификация транзакций», разделы 2-4). Раньше
    # tx_verified поднимался по одному факту, что транзакция найдена и не
    # провалилась — СУММА не сверялась вообще. Теперь «подтверждено»
    # выставляется ТОЛЬКО после успешной сверки суммы; всё остальное — либо
    # расхождение, либо «не проверено».
    tx_state = GC.TX_STATE_NONE
    tx_amount = None
    tx_verified = False
    tx_company_match = False
    tx_verify_error = None
    if tx_hash:
        api_keys = {
            "tron": settings.tronscan_api_key or None,
            "ethereum": settings.etherscan_api_key or None,
            "bsc": settings.bscscan_api_key or None,
        }
        try:
            result = await GCV.verify_tx(tx_network, tx_hash, api_keys=api_keys)
        except Exception:  # noqa: BLE001
            logger.exception("guro_id: ончейн-верификация упала для tx_hash=%s", tx_hash)
            result = GCV.VerifyResult(False, error="VERIFY_CRASHED")
        tx_amount = result.amount
        tx_verify_error = result.error
        # Сверяем с той суммой, которую человек указал: сделка односторонняя,
        # заполнено одно из двух полей.
        declared = next((a for a in (amount_received, amount_paid) if a), None)
        # Давность (ТЗ «Hash_Uniqueness», раздел 5): слишком старую
        # транзакцию не подтверждаем, но и сделку не блокируем.
        fresh = GL.tx_within_age_limit(result.timestamp, datetime.now(timezone.utc))
        if result.verified and not fresh:
            tx_verify_error = "TX_TOO_OLD"
        elif result.verified:
            if GL.amounts_match(declared, result.amount):
                tx_state = GC.TX_STATE_VERIFIED
                tx_verified = True
                tx_company_match = GCV.matches_company_address(
                    result, tx_network, storage.verified_company_addresses(),
                )
            elif declared is None or result.amount is None:
                # Сверять не с чем (сумму не указали или не смогли разобрать
                # трансфер) — «подтверждено» тут ставить нельзя.
                tx_verify_error = tx_verify_error or "NO_AMOUNT_TO_COMPARE"
            else:
                tx_state = GC.TX_STATE_MISMATCH
                tx_verify_error = "AMOUNT_MISMATCH"
        elif result.error in ("NOT_FOUND", "TX_FAILED"):
            # Транзакции нет в сети либо она провалена — это расхождение,
            # человеку есть что показать (ТЗ раздел 4).
            tx_state = GC.TX_STATE_MISMATCH
        # Остальные ошибки (API недоступен, нет ключа, таймаут, падение) —
        # оставляем «не проверено». Считать сделку подтверждённой при
        # недоступном API нельзя ни при каких условиях (ТЗ раздел 4).
        logger.info(
            "guro_id: ончейн-проверка %s: состояние=%s заявлено=%s в сети=%s ошибка=%s",
            tx_hash[:16], tx_state, declared, result.amount, tx_verify_error,
        )

    try:
        partnership = storage.create_partnership(
            user["id"], target_profile["user_id"], vertical, geo,
            offer=offer, amount_received=amount_received, amount_paid=amount_paid,
            review=review, amount_visible=amount_visible, tx_hash=tx_hash,
            ptype=ptype, tx_network=tx_network, tx_verified=tx_verified,
            tx_state=tx_state, tx_amount=tx_amount,
            tx_company_match=tx_company_match, tx_verify_error=tx_verify_error,
            company_id=company_id, is_flagged_fraud=is_flagged_fraud,
            identity_visible=identity_visible,
        )
    except ValueError as e:
        return _reject(str(e), 409)

    initiator_profile = storage.get_profile(user["id"])
    initiator_username = (initiator_profile["username"] if initiator_profile else None) or user.get("username") or "?"
    try:
        await _notify_confirmer(settings.bot_token, target_profile["user_id"], initiator_username, partnership["id"])
    except Exception:  # noqa: BLE001
        logger.exception("guro_id: не удалось отправить уведомление о партнёрстве %s", partnership["id"])

    return web.json_response({"id": partnership["id"], "status": partnership["status"]})


async def _notify_new_message(bot_token: str, webapp_url: str, recipient_id: int, sender_id: int) -> None:
    """Уведомление о новом сообщении — БЕЗ содержимого (сохраняет приватность
    переписки внутри прилы, тот же принцип, что и весь модуль сообщений).
    Deep-link ?thread=<sender_id> открывает Mini App сразу на этой
    переписке (см. App.jsx::readDeepLinkThread), а не на общей вкладке."""
    url = f"{webapp_url.rstrip('/')}/?thread={sender_id}"
    bot = Bot(token=bot_token)
    async with bot:
        await bot.send_message(
            recipient_id,
            "✉️ Вам пришло новое сообщение в GURO ID.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Открыть сообщения", web_app=WebAppInfo(url=url)),
            ]]),
        )


async def _notify_vacancy_response(
    bot_token: str, webapp_url: str, author_id: int, vacancy_id: int,
    vacancy_title: str, candidate: str,
) -> None:
    """Уведомление владельцу вакансии о новом отклике (06.09.2026,
    «рекрутер полный.pdf», стр. 8). Deep-link ведёт сразу к откликам ЭТОЙ
    вакансии — та же механика, что у ?thread= для сообщений."""
    url = f"{webapp_url.rstrip('/')}/?responses={vacancy_id}"
    bot = Bot(token=bot_token)
    async with bot:
        await bot.send_message(
            author_id,
            f"↩️ Новый отклик на вакансию «{vacancy_title}» — {candidate}.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Посмотреть отклик", web_app=WebAppInfo(url=url)),
            ]]),
        )


_RATING_ERROR_STATUS = {
    "NOT_FOUND": 404, "NOT_YOUR_PARTNERSHIP": 403, "NOT_CONFIRMED": 409,
    "INVALID_VERDICT": 400, "RATING_NOT_FOUND": 404, "COMMENT_REQUIRED": 400,
}


async def handle_submit_rating(request: web.Request) -> web.Response:
    """Оценка партнёрства, Шаг 2 (ТЗ 6.1, 25.08.2026) — POST
    /api/partnerships/<id>/rate {"verdict", "comment"}. 25.08.2026: теперь
    UPSERT — тот же эндпоинт редактирует уже поставленную оценку (см.
    guro_storage.submit_rating)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        partnership_id = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    body = await request.json()
    verdict = str(body.get("verdict", "")).strip()
    comment = body.get("comment")

    try:
        row = storage.submit_rating(partnership_id, user["id"], verdict, comment)
    except ValueError as e:
        code = str(e)
        return web.json_response({"error": code}, status=_RATING_ERROR_STATUS.get(code, 409))
    return web.json_response({"id": row["id"], "rating_revealed": bool(row["rating_revealed_at"])})


async def handle_delete_rating(request: web.Request) -> web.Response:
    """Удаление своей оценки (25.08.2026, фидбек владельца) — POST
    /api/partnerships/<id>/rate/delete."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        partnership_id = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    try:
        storage.delete_rating(partnership_id, user["id"])
    except ValueError as e:
        code = str(e)
        return web.json_response({"error": code}, status=_RATING_ERROR_STATUS.get(code, 409))
    return web.json_response({"ok": True})


async def handle_pending_ratings(request: web.Request) -> web.Response:
    """Список ПОДТВЕРЖДЁННЫХ партнёрств, которые я ещё НЕ оценил — для
    экрана "Оцените ваши сделки" (не обязательно, но чтобы юзер знал, что
    есть что оценить)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    result = []
    for p in storage.list_confirmed_partnerships(user["id"]):
        if storage.get_my_rating(p["id"], user["id"]) is not None:
            continue
        other_id = p["confirmer_id"] if p["initiator_id"] == user["id"] else p["initiator_id"]
        other_profile = storage.get_profile(other_id)
        result.append({
            "id": p["id"],
            "user_id": other_id,
            "username": other_profile["username"] if other_profile else None,
            "name": other_profile["name"] if other_profile else None,
            "confirmed_at": p["confirmed_at"],
            "ptype": p["ptype"],
        })
    return web.json_response({"results": result})


async def handle_submit_company_address(request: web.Request) -> web.Response:
    """5.5 — компания привязывает свой крипто-адрес, ждёт ручного
    подтверждения модератором (см. handlers/admin_guro.py)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    if not storage.is_company_subscribed(user["id"]):
        return web.json_response({"error": "SUBSCRIPTION_REQUIRED"}, status=402)
    body = await request.json()
    network = str(body.get("network", "")).strip()
    address = str(body.get("address", "")).strip()
    try:
        row = storage.submit_company_address(user["id"], network, address)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    return web.json_response({"id": row["id"], "status": row["status"]})


async def handle_list_company_addresses(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    rows = storage.list_company_addresses(user["id"])
    return web.json_response({"results": [
        {"id": r["id"], "network": r["network"], "address": r["address"], "status": r["status"]}
        for r in rows
    ]})


def _next_utc_midnight_iso() -> str:
    """Раздел 3 ТЗ "Тарифы и лимиты" — "понятное сообщение, что именно
    исчерпано и когда обновится, не просто 'ошибка'". Все дневные лимиты
    сбрасываются по UTC 00:00 (та же граница, что уже использует
    profile_views_today)."""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return GL.format_db_datetime(tomorrow)


def _views_per_day_limit(storage: GuroStorage, user_id: int) -> int | None:
    """Раздел 2.1 ТЗ "Тарифы и лимиты" — тарифо-зависимый дневной лимит
    просмотров: Компания приоритетнее Рекрутера (если оплачены оба —
    действует более щедрый), тир Компании решает, какое число. None —
    лимита нет вообще (Личный Pro/бесплатный — раздел 2.1, "не
    ограничивается отдельно")."""
    if storage.is_company_subscribed(user_id):
        tier = storage.get_company_tier(user_id)
        if tier == GC.COMPANY_TIER_PRO:
            return storage.get_effective_limit(user_id, GC.LIMIT_KEY_VIEWS_COMPANY_PRO, GC.LIMIT_VIEWS_PER_DAY_COMPANY_PRO)
        return storage.get_effective_limit(user_id, GC.LIMIT_KEY_VIEWS_COMPANY_BASIC, GC.LIMIT_VIEWS_PER_DAY_COMPANY_BASIC)
    if storage.is_recruiter_subscribed(user_id):
        return storage.get_effective_limit(user_id, GC.LIMIT_KEY_VIEWS_RECRUITER, GC.LIMIT_VIEWS_PER_DAY_RECRUITER)
    return None


def _new_requests_per_day_limit(storage: GuroStorage, user_id: int) -> int:
    """Раздел 2.2 ТЗ "Тарифы и лимиты" — Компания приоритетнее Рекрутера
    (см. _views_per_day_limit — тот же принцип "более щедрый выигрывает"),
    но тут БЕЗ разницы Basic/Pro (ТЗ: "30 на аккаунт компании в целом",
    одно число для обоих тиров). База (Личный Pro/бесплатный) — 10."""
    if storage.is_company_subscribed(user_id):
        return storage.get_effective_limit(user_id, GC.LIMIT_KEY_REQUESTS_COMPANY, GC.LIMIT_NEW_REQUESTS_PER_DAY_COMPANY)
    if storage.is_recruiter_subscribed(user_id):
        return storage.get_effective_limit(user_id, GC.LIMIT_KEY_REQUESTS_RECRUITER, GC.LIMIT_NEW_REQUESTS_PER_DAY_RECRUITER)
    return storage.get_effective_limit(user_id, GC.LIMIT_KEY_REQUESTS_PERSONAL, GC.LIMIT_NEW_REQUESTS_PER_DAY_PERSONAL)


def _check_profile_view_limit(storage: GuroStorage, viewer_id: int, target_id: int) -> bool:
    """ТЗ 7 / ТЗ "Тарифы и лимиты" раздел 2.1 — рейт-лимит просмотра ЧУЖИХ
    полных карточек, только для подписчиков Рекрутер/Компания (обычные
    пользователи не лимитируются). True — можно смотреть (и просмотр
    залогирован); False — лимит исчерпан, вызывающий код должен вернуть 429."""
    if viewer_id == target_id:
        return True
    limit = _views_per_day_limit(storage, viewer_id)
    if limit is None:
        return True
    if storage.profile_views_today(viewer_id) >= limit:
        return False
    storage.log_profile_view(viewer_id, target_id)
    return True


def _other_display(profile) -> dict:
    return {
        "other_name": profile["name"] or (f"@{profile['username']}" if profile["username"] else None),
        "other_username": profile["username"],
    }


async def handle_list_messages(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    threads = storage.list_threads(user["id"])
    result = []
    for t in threads:
        other_profile = storage.get_profile(t["other_user_id"])
        result.append({
            "other_user_id": t["other_user_id"],
            **(_other_display(other_profile) if other_profile else {"other_name": None, "other_username": None}),
            "last_message": t["last_message"],
            "last_message_at": t["last_message_at"],
            "unread_count": t["unread_count"],
        })
    return web.json_response({"threads": result})


async def handle_get_thread(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        other_id = int(request.match_info["user_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    other_profile = storage.get_profile(other_id)
    if other_profile is None:
        return web.json_response({"error": "NOT_FOUND"}, status=404)

    thread = storage.find_thread(user["id"], other_id)
    messages = []
    if thread is not None:
        messages = [
            {
                "id": m["id"], "sender_id": m["sender_id"], "body": m["body"],
                "created_at": m["created_at"], "mine": m["sender_id"] == user["id"],
                # Метка кабинета-источника (2.7, ТЗ "Гуро рекрутер каб",
                # "единый инбокс") — через какой кабинет ОТПРАВИТЕЛЬ писал.
                "via_workspace": m["via_workspace"] or "personal",
            }
            for m in storage.list_messages(thread["id"])
        ]
        storage.mark_thread_read(thread["id"], user["id"])

    return web.json_response({
        "other_user_id": other_id,
        **_other_display(other_profile),
        "messages": messages,
        # Тред уже есть -> отвечать можно всегда; нового треда ещё нет ->
        # писать первым можно, только если у СМОТРЯЩЕГО (сам user) есть
        # ЛЮБАЯ активная подписка — личная/рекрутер/компания.
        "can_send_first": thread is not None or storage.any_subscription_active(user["id"]),
    })


_MESSAGE_ERROR_STATUS = {
    "SELF_MESSAGE": 400,
    "EMPTY_BODY": 400,
    "NO_RECIPIENT_PROFILE": 404,
    "SUBSCRIPTION_REQUIRED": 402,
    "RATE_LIMITED": 429,
}


_MESSAGE_WORKSPACES = ("personal", "recruiter", "company")


async def handle_send_message(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    text = str(body.get("body", ""))
    try:
        recipient_id = int(body.get("recipient_id"))
    except (TypeError, ValueError):
        return web.json_response({"error": "NO_RECIPIENT_PROFILE"}, status=404)
    via_workspace = str(body.get("via_workspace", "personal")).strip()
    if via_workspace not in _MESSAGE_WORKSPACES:
        via_workspace = "personal"

    try:
        message = storage.send_message(user["id"], recipient_id, text, via_workspace=via_workspace)
    except ValueError as e:
        code = str(e)
        return web.json_response({"error": code}, status=_MESSAGE_ERROR_STATUS.get(code, 400))

    try:
        await _notify_new_message(settings.bot_token, settings.guro_id_webapp_url, recipient_id, user["id"])
    except Exception:  # noqa: BLE001
        logger.exception("guro_id: не удалось уведомить о новом сообщении user_id=%s", recipient_id)

    return web.json_response({"id": message["id"], "created_at": message["created_at"]})


async def handle_set_privacy(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    field = str(body.get("field", ""))
    value = bool(body.get("value"))
    try:
        privacy = storage.set_privacy_field(user["id"], field, value)
    except ValueError:
        return web.json_response({"error": "UNKNOWN_FIELD"}, status=400)
    return web.json_response(privacy)


async def handle_set_anketa_field(request: web.Request) -> web.Response:
    """Правка полей САМОЙ анкеты из приложения (09.09.2026, просьба
    владельца): имя, компания, должность, вертикаль, грейд.

    Вертикаль и грейд принимаются только из справочника — по ним работает
    поиск, и свободный текст сделал бы человека ненаходимым (см.
    GC.ANKETA_CHOICE_FIELDS).
    """
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    field = _body_text(body, "field").strip()
    value = _body_text(body, "value").strip()[:200] or None

    if field in GC.ANKETA_CHOICE_FIELDS:
        allowed = C.VERTICALS if field == "vertical" else C.GRADES + (C.INVESTOR_GRADE,)
        if value is not None and value not in allowed:
            return web.json_response({"error": "INVALID_VALUE"}, status=400)
    elif field not in GC.ANKETA_EDITABLE_FIELDS:
        return web.json_response({"error": "UNKNOWN_FIELD"}, status=400)

    try:
        storage.update_profile_field(user["id"], field, value)
    except ValueError:
        return web.json_response({"error": "NO_PROFILE"}, status=404)
    # Контракт shared-компонента EditableField (Shared.jsx): onSaved(updated[field])
    # ждёт значение ПОД КЛЮЧОМ ИМЕНИ ПОЛЯ — как у трёх сестринских эндпоинтов
    # (set_extra/set_recruiter_extra/set_company_extra_field). Раньше тут было
    # {"field": field, "value": value} — для поля "name" фронт делал updated["name"],
    # получал undefined и стирал только что сохранённый текст с экрана сразу
    # после сохранения (11.09.2026, баг-репорт: "после заполнения и попытки
    # сохранить данные отображаются как незаполненные, но при переходе туда и
    # обратно всё на месте" — то есть в БД всё верно, ломался только отклик).
    return web.json_response({field: value})


async def handle_set_profile_field(request: web.Request) -> web.Response:
    """Редактирование НОВЫХ полей профиля (GC.EXTRA_PROFILE_FIELDS: CV-текст,
    сайт, "чем полезен"). В отличие от полей анкеты (только чтение в Mini
    App, источник — бот), для этих полей другого способа заполнения нет,
    поэтому редактируются прямо здесь."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    field = str(body.get("field", ""))
    # value:null (12.09.2026, "удалить фото") — _body_text отличает
    # "ключа нет" от "ключ есть, значение null"; str(body.get(...)) этого
    # не умеет и превращает null в буквальную строку "None".
    value = _body_text(body, "value").strip()[:2000] or None
    try:
        extra = storage.set_extra_profile_field(user["id"], field, value)
    except ValueError:
        return web.json_response({"error": "UNKNOWN_FIELD"}, status=400)
    return web.json_response(extra)


async def handle_set_recruiter_profile_field(request: web.Request) -> web.Response:
    """Редактирование витрины кабинета рекрутера (Фаза 3) — отдельный
    эндпоинт, а не workspace= у /api/profile, чтобы не разводить в одном
    хендлере два разных набора допустимых полей и таблиц."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    field = str(body.get("field", ""))
    # value:null (12.09.2026, "удалить логотип") — см. комментарий у
    # handle_set_profile_field выше.
    value = _body_text(body, "value").strip()[:2000] or None
    try:
        extra = storage.set_recruiter_extra_field(user["id"], field, value)
    except ValueError:
        return web.json_response({"error": "UNKNOWN_FIELD"}, status=400)
    return web.json_response(extra)


async def handle_set_recruiter_privacy(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    field = str(body.get("field", ""))
    value = bool(body.get("value"))
    try:
        privacy = storage.set_recruiter_privacy_field(user["id"], field, value)
    except ValueError:
        return web.json_response({"error": "UNKNOWN_FIELD"}, status=400)
    return web.json_response(privacy)


async def handle_set_company_profile_field(request: web.Request) -> web.Response:
    """Редактирование витрины кабинета "Компания" (16.08.2026) — зеркало
    handle_set_recruiter_profile_field выше. 27.08.2026 (ТЗ "Роли и команда",
    раздел 2) — Владелец И Админ/Рекрутер редактируют НАРАВНЕ, требуется
    только членство в компании (любая роль), не конкретно владение."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    membership = storage.get_company_membership(user["id"])
    if membership is None:
        return web.json_response({"error": "NOT_A_COMPANY_MEMBER"}, status=403)
    company_id = membership["company_id"]
    body = await request.json()
    field = str(body.get("field", ""))
    # value:null (12.09.2026, "удалить логотип/обложку") — см. комментарий
    # у handle_set_profile_field выше.
    value = _body_text(body, "value").strip()[:2000] or None
    try:
        extra = storage.set_company_extra_field(company_id, field, value)
    except ValueError:
        return web.json_response({"error": "UNKNOWN_FIELD"}, status=400)
    # "Тип компании" -> "Другое" (26.08.2026, ТЗ "Компания. каб", раздел 5) —
    # не сразу в справочник, логируется для последующего review, та же
    # логика, что у нестандартных должностей вакансий.
    if field == "company_type_other" and value:
        storage.log_company_other_type(company_id, value)
    # Раздел 1.2 ТЗ "Роли и команда" — "система проверяет на совпадение по
    # названию, нестрогое сравнение". Мягкое предупреждение, НЕ блокирует
    # сохранение (см. GuroStorage.find_similar_companies) — в ТЗ не описан
    # явный блокирующий сценарий, а не давать сохранить уже введённое имя
    # было бы хуже пустого предупреждения.
    if field == "name" and value:
        similar = storage.find_similar_companies(value, exclude_company_id=company_id)
        if similar:
            extra = dict(extra)
            extra["similar_companies"] = [{"name": r["name"]} for r in similar[:5]]
    return web.json_response(extra)


async def handle_upload_company_image(request: web.Request) -> web.Response:
    """Загрузка лого/обложки компании файлом (28.08.2026, фидбек владельца:
    раньше можно было только вставить готовую ссылку — теперь выбор из
    галереи прямо в Mini App). Права — как у handle_set_company_profile_
    field выше (любой участник команды, не только владелец). multipart:
    поле "kind" (logo|cover) + поле "file". Имя файла на диске НИКОГДА не
    берётся у клиента (path traversal) — company_id+kind+хэш содержимого,
    расширение — по реально сработавшей сигнатуре, не по имени/Content-Type
    из запроса (см. _sniff_image_ext)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    membership = storage.get_company_membership(user["id"])
    if membership is None:
        return web.json_response({"error": "NOT_A_COMPANY_MEMBER"}, status=403)
    company_id = membership["company_id"]

    kind = None
    file_bytes = b""
    reader = await request.multipart()
    async for part in reader:
        if part.name == "kind":
            kind = (await part.text()).strip()
        elif part.name == "file":
            file_bytes = await part.read(decode=False)

    if kind not in ("logo", "cover"):
        return web.json_response({"error": "INVALID_KIND"}, status=400)
    if not file_bytes:
        return web.json_response({"error": "EMPTY_FILE"}, status=400)
    if len(file_bytes) > COMPANY_UPLOAD_MAX_BYTES[kind]:
        return web.json_response({"error": "FILE_TOO_LARGE"}, status=400)
    ext = _sniff_image_ext(file_bytes)
    if ext is None:
        return web.json_response({"error": "UNSUPPORTED_FORMAT"}, status=400)

    digest = hashlib.sha256(file_bytes).hexdigest()[:20]
    filename = f"{company_id}_{kind}_{digest}.{ext}"
    COMPANY_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    (COMPANY_UPLOADS_DIR / filename).write_bytes(file_bytes)

    field = "logo_url" if kind == "logo" else "cover_url"
    url = f"/uploads/company/{filename}"
    extra = storage.set_company_extra_field(company_id, field, url)
    return web.json_response(extra)


async def handle_upload_recruiter_image(request: web.Request) -> web.Response:
    """Логотип кабинета Рекрутер из галереи — зеркало
    handle_upload_company_image, но вид один (обложка кабинета рекрутера —
    градиент в CSS, а не картинка) и своя папка: имена файлов там строятся
    от company_id, тут от user_id, в общей папке они бы столкнулись.

    Гейт по подписке, в отличие от текстового
    handle_set_recruiter_profile_field: тут на диск ложится файл, а сам
    кабинет и так доступен только подписчикам.

    Имя файла НЕ берётся у клиента (path traversal) — user_id + хэш
    содержимого, расширение по реально сработавшей сигнатуре."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    if not storage.is_recruiter_subscribed(user["id"]):
        return web.json_response({"error": "NOT_SUBSCRIBED"}, status=403)

    file_bytes = b""
    reader = await request.multipart()
    async for part in reader:
        if part.name == "file":
            file_bytes = await part.read(decode=False)

    if not file_bytes:
        return web.json_response({"error": "EMPTY_FILE"}, status=400)
    if len(file_bytes) > COMPANY_UPLOAD_MAX_BYTES["logo"]:
        return web.json_response({"error": "FILE_TOO_LARGE"}, status=400)
    ext = _sniff_image_ext(file_bytes)
    if ext is None:
        return web.json_response({"error": "UNSUPPORTED_FORMAT"}, status=400)

    digest = hashlib.sha256(file_bytes).hexdigest()[:20]
    filename = f"{user['id']}_logo_{digest}.{ext}"
    RECRUITER_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    (RECRUITER_UPLOADS_DIR / filename).write_bytes(file_bytes)

    url = f"/uploads/recruiter/{filename}"
    extra = storage.set_recruiter_extra_field(user["id"], "logo_url", url)
    return web.json_response(extra)


async def handle_request_company_verification(request: web.Request) -> web.Response:
    """Кнопка "Подать заявку на верификацию" (раздел 2 ТЗ) — MVP: только
    фиксирует время запроса, реальная сверка домена/бренда — вручную
    администратором в /admin (handlers/admin_guro.py, см. раздел 2 ТЗ)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    membership = storage.get_company_membership(user["id"])
    if membership is None:
        return web.json_response({"error": "NOT_A_COMPANY_MEMBER"}, status=403)
    storage.request_company_verification(membership["company_id"])
    return web.json_response({"ok": True})


async def handle_set_company_privacy(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    membership = storage.get_company_membership(user["id"])
    if membership is None:
        return web.json_response({"error": "NOT_A_COMPANY_MEMBER"}, status=403)
    body = await request.json()
    field = str(body.get("field", ""))
    value = bool(body.get("value"))
    try:
        privacy = storage.set_company_privacy_field(membership["company_id"], field, value)
    except ValueError:
        return web.json_response({"error": "UNKNOWN_FIELD"}, status=400)
    return web.json_response(privacy)


def _company_match_public(storage: GuroStorage, row) -> dict:
    """Карточка найденной компании для экрана создания (раздел 3.0.1).
    company_id обязателен: на нём держится кнопка «Запросить
    присоединение», без него человеку снова пришлось бы искать компанию
    руками через поиск или доску вакансий."""
    company_id = row["user_id"]
    extra = storage.get_company_extra(company_id)
    return {
        "company_id": company_id,
        "name": row["name"],
        "vertical": extra.get("vertical"),
        "logo_url": extra.get("logo_url"),
        "verified": bool(storage.is_company_verified(company_id)),
    }


async def handle_company_name_check(request: web.Request) -> web.Response:
    """Раздел 3.0.1 — проверка названия ДО оплаты и до создания. Ничего не
    создаёт и не меняет: это ответ на вопрос «такая компания уже есть?»,
    который фронт задаёт, пока человек ещё печатает."""
    settings, storage = request.app["settings"], request.app["storage"]
    _auth(request, settings)
    name = request.query.get("name", "").strip()[:200]
    if not name:
        return web.json_response({"matches": []})
    matches = storage.find_similar_companies(name)
    return web.json_response({
        "matches": [_company_match_public(storage, row) for row in matches[:5]],
    })


async def handle_create_company(request: web.Request) -> web.Response:
    """Явное создание компании (раздел 1 ТЗ "Роли и управление командой") —
    основатель сразу становится Владельцем (см. GuroStorage.
    get_or_create_company_profile — заводит и профиль, и membership-строку
    role=owner одним вызовом). similar_companies — раздел 1.2 ТЗ, мягкое
    предупреждение о похожем названии, НЕ блокирует создание."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    if storage.get_company_membership(user["id"]) is not None:
        return web.json_response({"error": "ALREADY_IN_COMPANY"}, status=409)
    body = await request.json()
    name = str(body.get("name", "")).strip()[:200]
    if not name:
        return web.json_response({"error": "NAME_REQUIRED"}, status=400)
    similar = storage.find_similar_companies(name)
    # Раздел 3.0.1: занятое название ведёт к присоединению, а не к созданию
    # второй такой же компании и оплате ненужного тарифа. Раньше совпадение
    # было мягким предупреждением ПОСЛЕ создания.
    if similar and not body.get("confirm_different"):
        return web.json_response({
            "error": "COMPANY_NAME_TAKEN",
            "matches": [_company_match_public(storage, row) for row in similar[:5]],
        }, status=409)
    storage.get_or_create_company_profile(user["id"])
    storage.set_company_extra_field(user["id"], "name", name)
    for field in ("vertical", "website", "description", "logo_url", "cover_url", "company_types", "company_type_other"):
        if field in body:
            value = str(body.get(field, "")).strip()[:2000] or None
            try:
                storage.set_company_extra_field(user["id"], field, value)
            except ValueError:
                pass
    summary = _company_summary(storage, user["id"])
    if similar:
        summary["similar_companies"] = [{"name": r["name"]} for r in similar[:5]]
    return web.json_response(summary)


async def _notify_user(bot_token: str, user_id: int, text: str) -> None:
    bot = Bot(token=bot_token)
    async with bot:
        await bot.send_message(user_id, text)


async def handle_company_join_request(request: web.Request) -> web.Response:
    """Раздел 3.1 ТЗ "Роли и команда" — кнопка "Запросить присоединение" на
    карточке чужой компании; company_id берётся с той же карточки (см.
    _company_profile_response). Уведомление уходит Владельцу — по аналогии
    с уже существующим _notify_confirmer (см. раздел 3.1, п.4 ТЗ)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    try:
        company_id = int(body.get("company_id"))
    except (TypeError, ValueError):
        return web.json_response({"error": "COMPANY_NOT_FOUND"}, status=404)
    position_text = _body_text(body, "position_text").strip()[:200] or None
    try:
        req = storage.create_join_request(company_id, user["id"], position_text)
    except ValueError as e:
        code = str(e)
        status = 404 if code == "COMPANY_NOT_FOUND" else 409
        return web.json_response({"error": code}, status=status)

    owner_row = next(
        (m for m in storage.list_company_members(company_id) if m["role"] == GC.COMPANY_ROLE_OWNER), None,
    )
    if owner_row is not None:
        requester_profile = storage.get_profile(user["id"])
        requester_name = (requester_profile["username"] if requester_profile else None) or f"id{user['id']}"
        company_extra = storage.get_company_extra(company_id)
        text = f"📥 Новый запрос на присоединение к команде «{company_extra.get('name') or 'вашей компании'}»: @{requester_name}"
        if position_text:
            text += f" — {position_text}"
        text += "."
        try:
            await _notify_user(settings.bot_token, owner_row["user_id"], text)
        except Exception:  # noqa: BLE001
            logger.exception("guro_id: не удалось уведомить владельца компании %s о заявке", company_id)
    return web.json_response({"id": req["id"], "status": req["status"]})


async def handle_get_company_team(request: web.Request) -> web.Response:
    """Экран "Команда" (раздел 3.2 ТЗ) — участники видны всем участникам,
    заявки на присоединение — только Владельцу (Админ их не видит)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    membership = storage.get_company_membership(user["id"])
    if membership is None:
        return web.json_response({"error": "NOT_A_COMPANY_MEMBER"}, status=403)
    company_id = membership["company_id"]
    members = storage.list_company_members(company_id)
    out_members = []
    for m in members:
        profile = storage.get_profile(m["user_id"])
        out_members.append({
            "user_id": m["user_id"],
            "role": m["role"],
            "position_text": m["position_text"],
            "name": profile["name"] if profile else None,
            "username": profile["username"] if profile else None,
            "joined_at": m["joined_at"],
        })
    data = {
        "company_id": company_id,
        "my_role": membership["role"],
        "my_user_id": user["id"],
        "member_count": len(members),
        "member_limit": storage.company_member_limit(company_id),
        "members": out_members,
    }
    if membership["role"] == GC.COMPANY_ROLE_OWNER:
        requests_rows = storage.list_join_requests(company_id, status=GC.JOIN_REQUEST_PENDING)
        out_requests = []
        for r in requests_rows:
            profile = storage.get_profile(r["user_id"])
            out_requests.append({
                "id": r["id"],
                "user_id": r["user_id"],
                "position_text": r["position_text"],
                "name": profile["name"] if profile else None,
                "username": profile["username"] if profile else None,
                "created_at": r["created_at"],
            })
        data["requests"] = out_requests
        approvals_limit = storage.get_effective_limit(
            company_id, GC.LIMIT_KEY_COMPANY_APPROVALS_PER_DAY, GC.LIMIT_COMPANY_APPROVALS_PER_DAY,
        )
        data["approvals_left_today"] = max(0, approvals_limit - storage.count_new_company_approvals_today(company_id))
    return web.json_response(data)


_TEAM_ERROR_STATUS = {
    "NOT_FOUND": 404, "NOT_OWNER": 403, "APPLICANT_ALREADY_IN_COMPANY": 409,
    "MEMBER_LIMIT_REACHED": 409, "DAILY_APPROVAL_LIMIT_REACHED": 429,
}


async def handle_approve_join_request(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        request_id = int(request.match_info["request_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    req_before = storage.get_join_request(request_id)
    try:
        req = storage.approve_join_request(request_id, user["id"])
    except ValueError as e:
        code = str(e)
        error_body = {"error": code}
        if code == "DAILY_APPROVAL_LIMIT_REACHED":
            error_body["resets_at"] = _next_utc_midnight_iso()
        if code == "MEMBER_LIMIT_REACHED" and req_before is not None:
            error_body["limit"] = storage.company_member_limit(req_before["company_id"])
        return web.json_response(error_body, status=_TEAM_ERROR_STATUS.get(code, 400))
    try:
        company_extra = storage.get_company_extra(req["company_id"])
        await _notify_user(
            settings.bot_token, req["user_id"],
            f"✅ «{company_extra.get('name') or 'Компания'}» подтвердил(а) ваше присоединение к команде в GURO ID.",
        )
    except Exception:  # noqa: BLE001
        logger.exception("guro_id: не удалось уведомить %s об одобрении заявки", req["user_id"])
    return web.json_response({"id": req["id"], "status": req["status"]})


async def handle_reject_join_request(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        request_id = int(request.match_info["request_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    if not storage.reject_join_request(request_id, user["id"]):
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    return web.json_response({"status": "rejected"})


async def handle_remove_company_member(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    membership = storage.get_company_membership(user["id"])
    if membership is None:
        return web.json_response({"error": "NOT_A_COMPANY_MEMBER"}, status=403)
    try:
        target_id = int(request.match_info["user_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    if not storage.remove_company_member(membership["company_id"], user["id"], target_id):
        return web.json_response({"error": "NOT_ALLOWED"}, status=403)
    try:
        company_extra = storage.get_company_extra(membership["company_id"])
        await _notify_user(
            settings.bot_token, target_id,
            f"👋 Вас удалили из команды «{company_extra.get('name') or 'компании'}» в GURO ID. "
            "История ваших подтверждённых сделок сохранена в вашем профиле.",
        )
    except Exception:  # noqa: BLE001
        logger.exception("guro_id: не удалось уведомить %s об удалении из команды", target_id)
    return web.json_response({"ok": True})


async def handle_transfer_company_ownership(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    membership = storage.get_company_membership(user["id"])
    if membership is None:
        return web.json_response({"error": "NOT_A_COMPANY_MEMBER"}, status=403)
    try:
        target_id = int(request.match_info["user_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    if not storage.transfer_company_ownership(membership["company_id"], user["id"], target_id):
        return web.json_response({"error": "NOT_ALLOWED"}, status=403)
    try:
        company_extra = storage.get_company_extra(membership["company_id"])
        name = company_extra.get("name") or "компании"
        await _notify_user(settings.bot_token, target_id, f"👑 Вы стали Владельцем «{name}» в GURO ID.")
        await _notify_user(settings.bot_token, user["id"], f"ℹ️ Вы передали роль Владельца «{name}» другому участнику.")
    except Exception:  # noqa: BLE001
        logger.exception("guro_id: не удалось уведомить о передаче владения компанией %s", membership["company_id"])
    return web.json_response({"ok": True})


async def handle_set_work_status(request: web.Request) -> web.Response:
    """Публичный статус трудоустройства (looking/neutral/working/выкл) —
    НЕ через generic set_extra_profile_field, т.к. это не свободный текст,
    а закрытый набор значений (GC.WORK_STATUS_VALUES)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    raw = body.get("status")
    value = str(raw).strip() if raw else None
    try:
        result = storage.set_work_status(user["id"], value)
    except ValueError:
        return web.json_response({"error": "INVALID_STATUS"}, status=400)
    return web.json_response({"work_status": result})


async def handle_set_recruiter_activity_status(request: web.Request) -> web.Response:
    """Статус активности кабинета "Рекрутер" (2.4, ТЗ "Гуро рекрутер каб") —
    hiring/not_hiring/выкл, отдельный от work_status личного профиля."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    raw = body.get("status")
    value = str(raw).strip() if raw else None
    try:
        result = storage.set_recruiter_activity_status(user["id"], value)
    except ValueError:
        return web.json_response({"error": "INVALID_STATUS"}, status=400)
    return web.json_response({"activity_status": result})


async def handle_set_cv_field(request: web.Request) -> web.Response:
    """Простые текстовые поля CV (GC.CV_SIMPLE_FIELDS) — вертикали/локация/
    навыки/языки/сертификаты. Должность и грейд — отдельные эндпоинты
    (своя валидация), см. handle_set_cv_profession/handle_set_cv_grade."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    field = str(body.get("field", ""))
    value = str(body.get("value", "")).strip()[:2000] or None
    try:
        extra = storage.set_cv_field(user["id"], field, value)
    except ValueError:
        return web.json_response({"error": "UNKNOWN_FIELD"}, status=400)
    return web.json_response(extra)


async def handle_set_cv_profession(request: web.Request) -> web.Response:
    """Смена должности — не чаще CV_PROFESSION_MAX_CHANGES_PER_YEAR раз в
    год (владелец, 2Правки СV.pdf), первое заполнение пустого поля не
    считается сменой (см. GuroStorage.set_cv_profession)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    value = str(body.get("value", "")).strip()[:200]
    if not value:
        return web.json_response({"error": "VALUE_REQUIRED"}, status=400)
    try:
        extra = storage.set_cv_profession(user["id"], value)
    except ValueError:
        return web.json_response({"error": "CHANGE_LIMIT_REACHED"}, status=400)
    return web.json_response(extra)


async def handle_set_cv_grade(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    raw = body.get("value")
    value = str(raw).strip() if raw else None
    try:
        extra = storage.set_cv_grade(user["id"], value)
    except ValueError:
        return web.json_response({"error": "INVALID_GRADE"}, status=400)
    return web.json_response(extra)


async def handle_set_cv_flag(request: web.Request) -> web.Response:
    """Тристейт да/нет/не указано — релокейт и полиграф."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    field = str(body.get("field", ""))
    raw = body.get("value")
    value = None if raw is None else bool(raw)
    try:
        extra = storage.set_cv_flag(user["id"], field, value)
    except ValueError:
        return web.json_response({"error": "UNKNOWN_FIELD"}, status=400)
    return web.json_response(extra)


async def handle_set_cv_salary(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    extra = storage.set_cv_salary(
        user["id"],
        salary_from=_parse_amount(body.get("salary_from")),
        salary_to=_parse_amount(body.get("salary_to")),
        negotiable=bool(body.get("negotiable")),
    )
    return web.json_response(extra)


def _cv_experience_public(row) -> dict:
    return {
        "id": row["id"],
        "company": row["company"],
        "position": row["position"],
        "date_from": row["date_from"],
        "date_to": row["date_to"],
        "location": row["location"],
        "description": row["description"],
    }


async def handle_add_cv_experience(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    company = str(body.get("company", "")).strip()[:200]
    position = str(body.get("position", "")).strip()[:200]
    if not company or not position:
        return web.json_response({"error": "COMPANY_AND_POSITION_REQUIRED"}, status=400)
    try:
        entry = storage.add_cv_experience(
            user["id"],
            company=company,
            position=position,
            date_from=str(body.get("date_from", "")).strip()[:50] or None,
            date_to=str(body.get("date_to", "")).strip()[:50] or None,
            location=str(body.get("location", "")).strip()[:200] or None,
            description=str(body.get("description", "")).strip()[:2000] or None,
        )
    except ValueError:
        return web.json_response({"error": "LIMIT_REACHED"}, status=400)
    return web.json_response(_cv_experience_public(entry))


async def handle_delete_cv_experience(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        entry_id = int(request.match_info["entry_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    if not storage.delete_cv_experience(entry_id, user["id"]):
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    return web.json_response({"status": "deleted"})


async def handle_get_qr(request: web.Request) -> web.Response:
    """Deep-link на /start бота с payload guro_<user_id> — сканирующий
    получает от бота сообщение с web_app-кнопкой на Mini App с этим
    профилем (см. handlers/flow.py::start). Не прямая ссылка на Mini App —
    для этого нужна регистрация short name через @BotFather, которой нет.

    ?workspace=recruiter (26.08.2026, ТЗ "Гуро рекрутер каб", "Мой QR") —
    суффикс "_r" в payload, сканирующий попадает сразу на РЕКРУТЕРСКУЮ
    карточку (см. handlers/flow.py::start), не личный профиль."""
    settings = request.app["settings"]
    user = _auth(request, settings)
    suffix = "_r" if request.query.get("workspace") == "recruiter" else ""
    deeplink = f"https://t.me/{settings.bot_username}?start={GC.QR_PAYLOAD_PREFIX}{user['id']}{suffix}"
    return web.json_response({"deeplink": deeplink})


async def handle_invite_link(request: web.Request) -> web.Response:
    """«Пригласить коллегу» (11.08.2026, Мои контакты) — персональная
    одноразовая реф-ссылка того же формата, что /invite в боте
    (handlers/referral.py::_referral_link, формат продублирован тут
    строкой ниже — не тянуть весь пакет handlers в отдельный процесс
    ради одного f-string). Слот резервируется в ГЛАВНОЙ Storage (реф-
    система общая для всего бота, не только GURO ID), тот же sqlite-файл,
    что и у GuroStorage, WAL уже включён под запись с двух процессов."""
    settings, main_storage = request.app["settings"], request.app["main_storage"]
    user = _auth(request, settings)
    slot = main_storage.create_referral_link(user["id"])
    link = f"https://t.me/{settings.bot_username}?start=ref_{user['id']}_{slot}"
    return web.json_response({"link": link})


def _vacancy_poster_summary(storage: GuroStorage, row) -> dict:
    """Кто разместил (раздел 2, "Кто разместил: имя/бренд + рейтинг") —
    берёт витрину из ТОГО кабинета, откуда была опубликована вакансия
    (author_workspace), плюс общий рейтинг (общий для всех воркспейсов,
    раздел 3 отдельного ТЗ по рекрутеру)."""
    workspace = row["author_workspace"] or "recruiter"
    if workspace == "company":
        extra = storage.get_company_extra(row["author_id"])
        # 26.08.2026 (ТЗ "Компания. каб", раздел 2): раньше тут ХАРДКОДИЛОСЬ
        # True для любой вакансии от компании — верификация только что
        # появилась в ТЗ, до этого не было реального статуса на бэкенде.
        # Теперь — настоящий ручной статус (см. GuroStorage.is_company_verified,
        # включается админом через handlers/admin_guro.py).
        name, verified = extra["name"], storage.is_company_verified(row["author_id"])
    else:
        extra = storage.get_recruiter_extra(row["author_id"])
        name, verified = extra["name"], False
    guro_user = storage.get_or_create_guro_user(row["author_id"])
    return {
        "author_workspace": workspace,
        "poster_name": name,
        "company": extra.get("company"),
        "verified_company": verified,
        # Логотип компании в компактной карточке доски (раздел 4 ТЗ
        # "Компания. каб") — только у вакансий от компании, у рекрутера-
        # одиночки миниатюры нет по спецификации (просто имя).
        "poster_logo_url": extra.get("logo_url") if workspace == "company" else None,
        "reputation_score": round(guro_user["reputation_score"], 1),
        "reputation_tier": GL.reputation_tier(guro_user["reputation_score"]),
    }


def _is_bookmarked(
    storage: GuroStorage, vacancy_id: int, viewer_id: int | None, bookmarked_ids: set[int] | None,
) -> bool:
    """Закладка вакансии для смотрящего. bookmarked_ids — уже готовый набор
    (списки вакансий тянут его ОДНИМ запросом, чтобы не делать по запросу
    на карточку); если его нет — точечная проверка."""
    if bookmarked_ids is not None:
        return vacancy_id in bookmarked_ids
    if viewer_id is None:
        return False
    return vacancy_id in storage.bookmarked_vacancy_ids(viewer_id)


def _vacancy_public(
    storage: GuroStorage, row, *, viewer_id: int | None = None, bookmarked_ids: set[int] | None = None,
) -> dict:
    """viewer_id (26.08.2026) — если передан и равен author_id (или, с
    27.08.2026, ТЗ "Роли и команда" — участник той же компании), подмешивает
    "владельческие" поля (счётчики просмотров/откликов, closed_reason) —
    та же карточка, публичная и "моя", просто с доп. полями для владельца
    (раздел 4/7, "Три состояния карточки")."""
    is_owner = viewer_id is not None and storage.vacancy_access_allowed(row, viewer_id)
    data = {
        "id": row["id"],
        "author_id": row["author_id"],
        **_vacancy_poster_summary(storage, row),
        "title": row["title"],
        "vertical": row["vertical"],
        "grade": row["grade"],
        "position": row["position"],
        "location": row["location"],
        "work_format": row["work_format"],
        "employment_type": row["employment_type"],
        "salary_from": row["salary_from"] if (row["salary_visible"] or is_owner) else None,
        "salary_to": row["salary_to"] if (row["salary_visible"] or is_owner) else None,
        "salary_negotiable": bool(row["salary_negotiable"]),
        "salary_visible": bool(row["salary_visible"]),
        "description": row["description"],
        "contact_method": row["contact_method"],
        "lang": row["lang"],
        "status": row["status"],
        "duration_days": row["duration_days"],
        "expires_at": row["expires_at"],
        "created_at": row["created_at"],
        "is_owner": is_owner,
        # Закладка (03.09.2026). В списках вызывающий передаёт готовый набор
        # id одним запросом (bookmarked_ids), в одиночных ручках его нет —
        # тогда спрашиваем точечно.
        "is_bookmarked": _is_bookmarked(storage, row["id"], viewer_id, bookmarked_ids),
    }
    if is_owner:
        data["views_count"] = row["views_count"]
        data["responses_count"] = storage.count_vacancy_responses(row["id"])
        data["closed_reason"] = row["closed_reason"]
        # published_by_user_id (27.08.2026, ТЗ "Роли и команда", раздел 6) —
        # "какой конкретно участник команды это сделал", для внутренней
        # аналитики компании; для recruiter-вакансий совпадает с author_id.
        data["published_by_user_id"] = row["published_by_user_id"] or row["author_id"]
    return data


async def handle_get_positions(request: web.Request) -> web.Response:
    """Справочник должностей (Вертикаль -> Грейд -> [должности]) — единый
    источник для анкеты регистрации (бот), фильтра "Должность" в Поиске и
    формы публикации вакансии (ТЗ "Recruitment — ВАКАНСИИ", Приложение)."""
    _auth(request, request.app["settings"])
    return web.json_response({"grades": list(GC.VACANCY_GRADES), "professions": PROFESSIONS})


async def handle_list_vacancies(request: web.Request) -> web.Response:
    """Просмотр доски — по БАЗОВОЙ подписке GURO ID (тот же пейволл, что и
    у остального поиска), публиковать может подписчик кабинета Рекрутер
    ИЛИ Компания (см. handle_create_vacancy)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    if not storage.is_subscribed(user["id"]):
        return web.json_response({"error": "SUBSCRIPTION_REQUIRED"}, status=402)
    lang = request.query.get("lang") or None
    vertical = request.query.get("vertical") or None
    grade = request.query.get("grade") or None
    position = request.query.get("position") or None
    query = request.query.get("q") or None
    company_type = request.query.get("company_type") or None
    bookmarked_ids = storage.bookmarked_vacancy_ids(user["id"])
    # bookmarked=1 — показать только сохранённые (фильтр доски, 03.09.2026).
    only_ids = bookmarked_ids if request.query.get("bookmarked") == "1" else None
    rows, truncated = storage.list_vacancies(
        lang=lang, vertical=vertical, grade=grade, position=position, query=query,
        company_type=company_type, only_ids=only_ids,
    )
    return web.json_response({
        "vacancies": [
            _vacancy_public(storage, r, viewer_id=user["id"], bookmarked_ids=bookmarked_ids) for r in rows
        ],
        "truncated": truncated,
    })


async def handle_my_vacancies(request: web.Request) -> web.Response:
    """Свои вакансии (включая закрытые/на паузе) — для управления, доступно
    любому (даже если подписка рекрутера/компании с тех пор истекла —
    старые публикации остаются видны владельцу для архивации).

    active_vacancies_limit (27.08.2026, ТЗ "экраны по ТЗ от 23.08", бейдж
    "N из M активных" в шапке "Мои вакансии") — сумма лимитов ПО ВСЕМ
    воркспейсам, где сейчас реально можно публиковать (обычно один, но
    участник команды компании может быть ОДНОВРЕМЕННО и рекрутером-
    подписчиком — тогда лимиты складываются, как и сами счётчики активных
    вакансий обоих кабинетов у него в списке)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    rows = storage.list_my_vacancies(user["id"])
    limit = 0
    if storage.is_recruiter_subscribed(user["id"]):
        limit += _active_vacancies_limit(storage, user["id"], "recruiter")
    membership = storage.get_company_membership(user["id"])
    if membership is not None and storage.is_company_subscribed(membership["company_id"]):
        limit += _active_vacancies_limit(storage, membership["company_id"], "company")
    return web.json_response({
        "vacancies": [_vacancy_public(storage, r, viewer_id=user["id"]) for r in rows],
        "active_vacancies_limit": limit,
    })


async def handle_get_vacancy(request: web.Request) -> web.Response:
    """Полная карточка (раздел 2.1) — увеличивает счётчик просмотров, если
    смотрит НЕ автор (см. GuroStorage.increment_vacancy_views)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        vacancy_id = int(request.match_info["vacancy_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    row = storage.get_vacancy(vacancy_id)
    if row is None:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    storage.increment_vacancy_views(vacancy_id, user["id"])
    row = storage.get_vacancy(vacancy_id)  # свежий views_count, если инкрементнули
    return web.json_response(_vacancy_public(storage, row, viewer_id=user["id"]))


def _parse_vacancy_fields(body: dict) -> dict:
    """Общий разбор полей формы публикации/редактирования (раздел 3 ТЗ) —
    используется и в create, и в edit."""
    out: dict = {}
    if "title" in body:
        out["title"] = str(body.get("title", "")).strip()[: GC.VACANCY_TITLE_MAX]
    if "vertical" in body:
        out["vertical"] = body.get("vertical") or None
    if "grade" in body:
        grade = body.get("grade") or None
        out["grade"] = grade if grade in GC.VACANCY_GRADES else None
    if "position" in body:
        out["position"] = str(body.get("position", "")).strip()[:200] or None
    if "position_is_other" in body:
        out["position_is_other"] = bool(body.get("position_is_other"))
    if "location" in body:
        out["location"] = str(body.get("location", "")).strip()[:200] or None
    if "work_format" in body:
        wf = body.get("work_format") or None
        out["work_format"] = wf if wf in GC.VACANCY_WORK_FORMATS else None
    if "employment_type" in body:
        et = body.get("employment_type") or None
        out["employment_type"] = et if et in GC.VACANCY_EMPLOYMENT_TYPES else None
    if "salary_from" in body:
        out["salary_from"] = _parse_amount(body.get("salary_from"))
    if "salary_to" in body:
        out["salary_to"] = _parse_amount(body.get("salary_to"))
    if "salary_negotiable" in body:
        out["salary_negotiable"] = bool(body.get("salary_negotiable"))
    if "salary_visible" in body:
        out["salary_visible"] = bool(body.get("salary_visible"))
    if "description" in body:
        out["description"] = str(body.get("description", "")).strip()[: GC.VACANCY_DESCRIPTION_MAX] or None
    if "contact_method" in body:
        cm = str(body.get("contact_method", GC.VACANCY_CONTACT_GURO_ID))
        out["contact_method"] = cm if cm in GC.VACANCY_CONTACT_METHODS else GC.VACANCY_CONTACT_GURO_ID
    if "contact_url" in body:
        out["contact_url"] = str(body.get("contact_url", "")).strip()[:500] or None
    if "lang" in body:
        lang = str(body.get("lang", "ru"))
        out["lang"] = lang if lang in GC.VACANCY_LANGS else "ru"
    return out


def _active_vacancies_limit(storage: GuroStorage, user_id: int, workspace: str) -> int:
    """Раздел 2.3 ТЗ "Тарифы и лимиты" — потолок ОДНОВРЕМЕННО активных
    вакансий, растёт с тарифом, считается ОТДЕЛЬНО на каждый кабинет."""
    if workspace == "company":
        tier = storage.get_company_tier(user_id)
        if tier == GC.COMPANY_TIER_PRO:
            return storage.get_effective_limit(
                user_id, GC.LIMIT_KEY_ACTIVE_VACANCIES_COMPANY_PRO, GC.LIMIT_ACTIVE_VACANCIES_COMPANY_PRO,
            )
        return storage.get_effective_limit(
            user_id, GC.LIMIT_KEY_ACTIVE_VACANCIES_COMPANY_BASIC, GC.LIMIT_ACTIVE_VACANCIES_COMPANY_BASIC,
        )
    return storage.get_effective_limit(
        user_id, GC.LIMIT_KEY_ACTIVE_VACANCIES_RECRUITER, GC.LIMIT_ACTIVE_VACANCIES_RECRUITER,
    )


async def handle_create_vacancy(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    # Публикует подписчик Рекрутер ИЛИ УЧАСТНИК компании (раздел 1 ТЗ;
    # 27.08.2026, ТЗ "Роли и команда" — Владелец и Админ/Рекрутер публикуют
    # наравне, см. vacancy_access_allowed). Воркспейс выбирает фронт явно.
    body = await request.json()
    author_workspace = str(body.get("author_workspace", "recruiter"))
    if author_workspace == "company":
        membership = storage.get_company_membership(user["id"])
        if membership is None or not storage.is_company_subscribed(membership["company_id"]):
            return web.json_response({"error": "COMPANY_SUBSCRIPTION_REQUIRED"}, status=402)
        limit_owner_id = membership["company_id"]
    else:
        author_workspace = "recruiter"
        if not storage.is_recruiter_subscribed(user["id"]):
            return web.json_response({"error": "RECRUITER_SUBSCRIPTION_REQUIRED"}, status=402)
        limit_owner_id = user["id"]

    # Раздел 2.3 ТЗ "Тарифы и лимиты" — два независимых лимита разом,
    # общих на ВСЮ команду компании (не персональных на участника).
    new_per_day = storage.get_effective_limit(limit_owner_id, GC.LIMIT_KEY_NEW_VACANCIES, GC.LIMIT_NEW_VACANCIES_PER_DAY)
    if storage.count_new_vacancies_today(limit_owner_id) >= new_per_day:
        return web.json_response(
            {"error": "DAILY_VACANCY_LIMIT_REACHED", "resets_at": _next_utc_midnight_iso()}, status=429,
        )
    active_limit = _active_vacancies_limit(storage, limit_owner_id, author_workspace)
    if storage.count_active_vacancies(limit_owner_id, workspace=author_workspace) >= active_limit:
        return web.json_response({"error": "ACTIVE_VACANCY_LIMIT_REACHED", "limit": active_limit}, status=429)

    fields = _parse_vacancy_fields(body)
    if not fields.get("title"):
        return web.json_response({"error": "TITLE_REQUIRED"}, status=400)
    duration_days = body.get("duration_days", GC.VACANCY_DURATION_DEFAULT)
    try:
        duration_days = int(duration_days)
    except (TypeError, ValueError):
        duration_days = GC.VACANCY_DURATION_DEFAULT
    if duration_days not in GC.VACANCY_DURATION_OPTIONS:
        duration_days = GC.VACANCY_DURATION_DEFAULT

    vacancy = storage.create_vacancy(
        limit_owner_id, author_workspace=author_workspace, duration_days=duration_days,
        published_by_user_id=user["id"],
        title=fields.get("title", ""), vertical=fields.get("vertical"), grade=fields.get("grade"),
        position=fields.get("position"), position_is_other=fields.get("position_is_other", False),
        location=fields.get("location"), work_format=fields.get("work_format"),
        employment_type=fields.get("employment_type"), salary_from=fields.get("salary_from"),
        salary_to=fields.get("salary_to"), salary_negotiable=fields.get("salary_negotiable", False),
        salary_visible=fields.get("salary_visible", False), description=fields.get("description"),
        contact_method=fields.get("contact_method", GC.VACANCY_CONTACT_GURO_ID),
        contact_url=fields.get("contact_url"), lang=fields.get("lang", "ru"),
    )
    return web.json_response(_vacancy_public(storage, vacancy, viewer_id=user["id"]))


async def handle_edit_vacancy(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        vacancy_id = int(request.match_info["vacancy_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    body = await request.json()
    fields = _parse_vacancy_fields(body)
    try:
        vacancy = storage.edit_vacancy(vacancy_id, user["id"], fields)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    if vacancy is None:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    if fields.get("position_is_other") and fields.get("position"):
        storage.log_vacancy_other_position(vacancy_id, vacancy["vertical"], vacancy["grade"], fields["position"])
    return web.json_response(_vacancy_public(storage, vacancy, viewer_id=user["id"]))


async def _vacancy_action(request: web.Request, action) -> web.Response:
    settings = request.app["settings"]
    storage = request.app["storage"]
    user = _auth(request, settings)
    try:
        vacancy_id = int(request.match_info["vacancy_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    ok = action(storage, vacancy_id, user["id"])
    if not ok:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    row = storage.get_vacancy(vacancy_id)
    return web.json_response(_vacancy_public(storage, row, viewer_id=user["id"]))


async def handle_bookmark_vacancy(request: web.Request) -> web.Response:
    """Переключатель закладки (03.09.2026) — отдельно от _vacancy_action:
    тот проверяет права ВЛАДЕЛЬЦА вакансии, а сохранить в закладки может
    любой подписчик, вакансия при этом чужая."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        vacancy_id = int(request.match_info["vacancy_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    state = storage.toggle_vacancy_bookmark(user["id"], vacancy_id)
    if state is None:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    return web.json_response({"is_bookmarked": state})


async def handle_pause_vacancy(request: web.Request) -> web.Response:
    return await _vacancy_action(request, lambda s, vid, uid: s.pause_vacancy(vid, uid))


async def handle_resume_vacancy(request: web.Request) -> web.Response:
    """Возобновление тоже сверяется с потолком одновременно активных
    (раздел 2.3 ТЗ "Тарифы и лимиты") — иначе можно обойти лимит паузой/
    возобновлением лишних вакансий вместо честного закрытия старых."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        vacancy_id = int(request.match_info["vacancy_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    row = storage.get_vacancy(vacancy_id)
    if row is None or not storage.vacancy_access_allowed(row, user["id"]):
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    workspace = row["author_workspace"] or "recruiter"
    # row["author_id"] — уже правильный "владелец лимита" в обоих случаях:
    # для recruiter-вакансии это сам человек, для company-вакансии — id
    # компании (лимит общий на всю команду, см. ТЗ "Роли и команда").
    active_limit = _active_vacancies_limit(storage, row["author_id"], workspace)
    if storage.count_active_vacancies(row["author_id"], workspace=workspace) >= active_limit:
        return web.json_response({"error": "ACTIVE_VACANCY_LIMIT_REACHED", "limit": active_limit}, status=429)
    if not storage.resume_vacancy(vacancy_id, user["id"]):
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    row = storage.get_vacancy(vacancy_id)
    return web.json_response(_vacancy_public(storage, row, viewer_id=user["id"]))


async def handle_extend_vacancy(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        vacancy_id = int(request.match_info["vacancy_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    body = await request.json()
    duration_days = body.get("duration_days", GC.VACANCY_DURATION_DEFAULT)
    try:
        duration_days = int(duration_days)
    except (TypeError, ValueError):
        duration_days = GC.VACANCY_DURATION_DEFAULT
    if duration_days not in GC.VACANCY_DURATION_OPTIONS:
        duration_days = GC.VACANCY_DURATION_DEFAULT
    if not storage.extend_vacancy(vacancy_id, user["id"], duration_days):
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    row = storage.get_vacancy(vacancy_id)
    return web.json_response(_vacancy_public(storage, row, viewer_id=user["id"]))


async def handle_close_vacancy(request: web.Request) -> web.Response:
    """closed_reason (раздел 4 ТЗ, "опциональная пометка 'Закрыта — нашли
    кандидата'") — необязательное короткое тело запроса."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        vacancy_id = int(request.match_info["vacancy_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    reason = None
    try:
        body = await request.json()
        reason = (_body_text(body, "reason").strip()[:200]) or None
    except Exception:  # noqa: BLE001
        pass
    if not storage.close_vacancy(vacancy_id, user["id"], reason=reason):
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    return web.json_response({"status": "closed"})


_RESPONSE_ERROR_STATUS = {
    "NOT_FOUND": 404, "NOT_ACTIVE": 409, "SELF_RESPONSE": 400,
    "ALREADY_RESPONDED": 409, "INVALID_STATUS": 400,
}


async def handle_respond_vacancy(request: web.Request) -> web.Response:
    """Отклик — один тап (раздел 5.1 ТЗ, "без сопроводительного письма") —
    message опционален. 28.08.2026: "внешняя ссылка" как способ связи убрана
    (см. GC.VACANCY_CONTACT_METHODS) — все вакансии теперь contact_method=
    guro_id, отклик всегда создаёт запись в системе."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        vacancy_id = int(request.match_info["vacancy_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    body = await request.json()
    message = (_body_text(body, "message").strip()[:500]) or None
    try:
        response = storage.create_vacancy_response(vacancy_id, user["id"], message)
    except ValueError as e:
        code = str(e)
        return web.json_response({"error": code}, status=_RESPONSE_ERROR_STATUS.get(code, 409))

    # Без этого рекрутер узнавал об отклике, только если сам заходил в
    # «Отклики» (стр. 8 отчёта). Сбой отправки не отменяет сам отклик —
    # он уже записан, и кандидат своё действие совершил.
    vacancy = storage.get_vacancy(vacancy_id)
    if vacancy is not None:
        profile = storage.get_profile(user["id"])
        candidate = (profile["name"] if profile else None) or (
            f"@{profile['username']}" if profile and profile["username"] else "кандидат"
        )
        try:
            await _notify_vacancy_response(
                settings.bot_token, settings.guro_id_webapp_url,
                vacancy["author_id"], vacancy_id, vacancy["title"], candidate,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "guro_id: не удалось уведомить об отклике на вакансию %s", vacancy_id,
            )

    return web.json_response({"id": response["id"], "status": response["status"]})


def _response_public(storage: GuroStorage, row) -> dict:
    profile = storage.get_profile(row["candidate_id"])
    guro_user = storage.get_or_create_guro_user(row["candidate_id"])
    out = {
        "id": row["id"],
        "vacancy_id": row["vacancy_id"],
        "candidate_id": row["candidate_id"],
        "candidate_name": profile["name"] if profile else None,
        "candidate_username": profile["username"] if profile else None,
        "candidate_vertical": profile["vertical"] if profile else None,
        "reputation_score": round(guro_user["reputation_score"], 1) if storage.is_subscribed(row["candidate_id"]) else None,
        "status": row["status"],
        "message": row["message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if "vacancy_title" in row.keys():
        out["vacancy_title"] = row["vacancy_title"]
    return out


async def handle_list_vacancy_responses(request: web.Request) -> web.Response:
    """Отклики ПО ОДНОЙ вакансии (раздел 5.2) — владелец или (27.08.2026,
    ТЗ "Роли и команда") любой участник той же компании."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        vacancy_id = int(request.match_info["vacancy_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    vacancy = storage.get_vacancy(vacancy_id)
    if vacancy is None or not storage.vacancy_access_allowed(vacancy, user["id"]):
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    status = request.query.get("status") or None
    rows = storage.list_vacancy_responses(vacancy_id, status=status)
    return web.json_response({
        "vacancy": _vacancy_public(storage, vacancy, viewer_id=user["id"]),
        "responses": [_response_public(storage, r) for r in rows],
    })


async def handle_list_my_responses(request: web.Request) -> web.Response:
    """Агрегированные отклики по ВСЕМ своим вакансиям (раздел 5.5,
    пункт "Отклики" на главном экране кабинета)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    status = request.query.get("status") or None
    rows = storage.list_responses_for_owner(user["id"], status=status)
    return web.json_response({"responses": [_response_public(storage, r) for r in rows]})


async def handle_update_response_status(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        response_id = int(request.match_info["response_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    body = await request.json()
    status = str(body.get("status", ""))
    try:
        row = storage.update_vacancy_response_status(response_id, user["id"], status)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    if row is None:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    return web.json_response(_response_public(storage, row))


# product -> тарифная сетка. Обобщено под ключ продукта (Фаза 3, 12.08.2026)
# вместо копипасты Stars+крипто-эндпоинтов под кабинет рекрутера — одна
# проверенная в проде платёжная цепочка на все продукты. company_basic/
# company_pro (27.08.2026, ТЗ "Тарифы и лимиты") — два ТИРА одного кабинета
# "Компания" реализованы как два отдельных product (см. GC.COMPANY_TIER_*),
# оба активируют ОДНУ И ТУ ЖЕ guro_company_profiles, просто с разным tier.
_PRODUCT_PLANS = {
    "guro_id": GC.SUBSCRIPTION_PLANS, "recruiter": GC.RECRUITER_SUBSCRIPTION_PLANS,
    "company_basic": GC.COMPANY_BASIC_SUBSCRIPTION_PLANS, "company_pro": GC.COMPANY_PRO_SUBSCRIPTION_PLANS,
}
_PRODUCT_PAYLOAD_PREFIX = {
    "guro_id": "guro_id_subscription", "recruiter": "guro_id_recruiter_subscription",
    "company_basic": "guro_id_company_basic_subscription", "company_pro": "guro_id_company_pro_subscription",
}
_PRODUCT_TITLE = {
    "guro_id": "GURO ID — подписка", "recruiter": "GURO ID — кабинет рекрутера",
    "company_basic": "GURO ID — кабинет компании Basic", "company_pro": "GURO ID — кабинет компании Pro",
}
_PRODUCT_DESCRIPTION = {
    "guro_id": "Полный поиск и просмотр профилей участников GURO ID: рейтинг, история партнёрств.",
    "recruiter": "Кабинет рекрутера GURO ID: отдельная витрина, публикация вакансий, просмотр резюме.",
    "company_basic": "Кабинет компании GURO ID (Basic, до 5 участников): бренд-страница работодателя.",
    "company_pro": "Кабинет компании GURO ID (Pro, до 15-20 участников): бренд-страница работодателя.",
}
# product -> tier, который activate_company_subscription запишет в
# guro_company_profiles.company_tier (только для company_basic/company_pro).
_PRODUCT_COMPANY_TIER = {"company_basic": GC.COMPANY_TIER_BASIC, "company_pro": GC.COMPANY_TIER_PRO}


def _plan_or_none(body: dict) -> tuple[str, str, dict] | None:
    product = str(body.get("product", "guro_id"))
    plans = _PRODUCT_PLANS.get(product)
    if plans is None:
        return None
    plan = str(body.get("plan", ""))
    cfg = plans.get(plan)
    return (product, plan, cfg) if cfg else None


async def handle_register(request: web.Request) -> web.Response:
    """Регистрация ПРЯМО в приложении (11.09.2026, «First-time flow»).

    Пишет в ТУ ЖЕ таблицу profiles, что и бот (main_storage.save_profile) —
    анкета из приложения неотличима от анкеты из бота ни для поиска, ни
    для платного входа, ни для админки. Набор полей — минимальное
    подмножество анкеты бота (вертикаль/грейд/профессия/имя); остальное
    донесётся позже через «Редактировать профиль». Грейд «Инвестор»
    (отдельные поля суммы/интересов) сюда не пускаем — только в боте.
    """
    settings = request.app["settings"]
    main_storage: Storage = request.app["main_storage"]
    user = _auth(request, settings)
    user_id = user["id"]

    if main_storage.has_profile(user_id):
        return web.json_response({"error": "ALREADY_REGISTERED"}, status=409)

    body = await request.json()
    name = _body_text(body, "name").strip()[:100]
    vertical = _body_text(body, "vertical").strip()
    grade = _body_text(body, "grade").strip()
    profession = _body_text(body, "profession").strip()

    if not name:
        return web.json_response({"error": "NAME_REQUIRED"}, status=400)
    if vertical not in C.VERTICALS:
        return web.json_response({"error": "INVALID_VERTICAL"}, status=400)
    if grade not in C.GRADES:
        return web.json_response({"error": "INVALID_GRADE"}, status=400)
    # Бот хранит МЕТКУ (label), не код (см. handlers/flow.py.pick_profession:
    # p["profession"] = label) — анкета из приложения должна писать то же
    # самое, иначе один и тот же человек хранился бы по-разному в зависимости
    # от того, откуда пришла анкета.
    valid_professions = {label for _, label in C.professions_for(vertical, grade)}
    if profession not in valid_professions:
        return web.json_response({"error": "INVALID_PROFESSION"}, status=400)

    lang = "en" if str(body.get("lang", "")) == "en" else "ru"
    profile = {
        "user_id": user_id, "username": user.get("username"),
        "vertical": vertical, "grade": grade, "profession": profession,
        "name": name, "lang": lang,
    }
    main_storage.save_profile(profile)

    # Баним ли — та же проверка, что у бота: анкета создаётся в любом
    # случае (человек остаётся в системе, видим его в админке), но
    # платный доступ такому не откроется НИКОГДА (см. handlers/flow.py и
    # _needs_payment, тот же принцип, что и в боте — просто пока без
    # отдельного экрана "banned_notice" в приложении, MVP).
    banned = main_storage.is_banned(user_id)

    card = MAIN_LOGIC.profile_to_admin_card(profile, banned=banned)
    try:
        async with Bot(token=settings.bot_token) as bot:
            for admin_id in settings.admin_ids:
                try:
                    await bot.send_message(
                        admin_id, card, parse_mode="HTML", disable_web_page_preview=True,
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("guro_id: notify admin %s failed", admin_id, exc_info=True)
    except Exception:  # noqa: BLE001
        logger.exception("guro_id: admin notify failed for in-app registration user_id=%s", user_id)

    return web.json_response({"ok": True, "banned": banned})


async def handle_get_plans(request: web.Request) -> web.Response:
    """Единый источник цен для фронта (Stars + крипто-эквивалент) — чтобы
    числа в UI никогда не разъезжались с тем, что реально спишут.
    crypto_enabled=False, пока владелец не пропишет CRYPTOBOT_API_TOKEN —
    фронт по этому флагу прячет кнопку крипто-оплаты, а не бьётся в 503.
    ?product=recruiter (Фаза 3) — тарифы кабинета рекрутера вместо базовых."""
    settings = request.app["settings"]
    product = request.query.get("product", "guro_id")
    plans_source = _PRODUCT_PLANS.get(product, GC.SUBSCRIPTION_PLANS)
    plans = {}
    for key, cfg in plans_source.items():
        plans[key] = {
            **cfg,
            "crypto_price_usd": round(cfg["stars_price"] * GC.STARS_TO_USD_RATE, 2),
            "crypto_asset": GC.CRYPTO_ASSET,
        }
        # 10.09.2026, крипта — основной способ оплаты: зачёркнутая полная
        # цена и «экономия» на карточке плана тоже в долларах.
        if cfg.get("stars_price_full"):
            plans[key]["crypto_price_usd_full"] = round(cfg["stars_price_full"] * GC.STARS_TO_USD_RATE, 2)
    # Скидка первого дня (11.09.2026) — только личная подписка, только
    # месяц. _auth() дёргаем ТОЛЬКО для guro_id, чтобы не менять поведение
    # тарифов рекрутера/компании (они как были без обязательной проверки
    # initData, так и остались) — фронт и так шлёт заголовок на каждый
    # запрос, лишней задержки это не добавляет.
    if product == "guro_id" and "monthly" in plans:
        # /api/plans остаётся публичным (без Authorization) — тест suite
        # это явно проверяет, и TariffsScreen может звать его до готовности
        # initData. Без валидной подписи просто не знаем, чей это день
        # регистрации, и скидку не показываем — не 401.
        try:
            user = _auth(request, settings)
        except web.HTTPUnauthorized:
            user = None
        if user and _first_day_discount_active(request.app["main_storage"], user["id"]):
            monthly = plans["monthly"]
            monthly["discount_pct"] = FIRST_DAY_DISCOUNT_PCT
            monthly["discount_stars_price"] = round(
                monthly["stars_price"] * (100 - FIRST_DAY_DISCOUNT_PCT) / 100
            )
            monthly["discount_crypto_price_usd"] = round(
                monthly["crypto_price_usd"] * (100 - FIRST_DAY_DISCOUNT_PCT) / 100, 2
            )
    return web.json_response({
        "plans": plans,
        "crypto_enabled": bool(settings.cryptobot_api_token or settings.cryptobot_api_token_new),
    })


async def handle_subscribe(request: web.Request) -> web.Response:
    settings = request.app["settings"]
    user = _auth(request, settings)
    body = await request.json()
    plan_triplet = _plan_or_none(body)
    if plan_triplet is None:
        return web.json_response({"error": "UNKNOWN_PLAN"}, status=400)
    product, plan, cfg = plan_triplet
    title = _PRODUCT_TITLE[product]

    # Скидка первого дня (11.09.2026) — см. _first_day_discount_active.
    stars_price = cfg["stars_price"]
    if product == "guro_id" and plan == "monthly" and \
            _first_day_discount_active(request.app["main_storage"], user["id"]):
        stars_price = round(stars_price * (100 - FIRST_DAY_DISCOUNT_PCT) / 100)

    bot = Bot(token=settings.bot_token)
    async with bot:
        link = await bot.create_invoice_link(
            title=f"{title} ({cfg['label'].lower()})",
            description=_PRODUCT_DESCRIPTION[product],
            payload=f"{_PRODUCT_PAYLOAD_PREFIX[product]}:{plan}:{user['id']}",
            provider_token=None,  # не нужен для Telegram Stars (Bot API 7.4+)
            currency="XTR",
            prices=[LabeledPrice(f"{title} — {cfg['label']}", stars_price)],
        )
    return web.json_response({"invoice_link": link})


async def handle_subscribe_crypto(request: web.Request) -> web.Response:
    """Альтернатива Stars — оплата подписки в крипте через CryptoBot (Crypto
    Pay API). Подтверждение приходит асинхронно вебхуком (handle_crypto_
    webhook), а не сразу в ответе, в отличие от Stars-инвойса."""
    settings, storage = request.app["settings"], request.app["storage"]
    picked = GCR.pick_token(settings, storage)
    if picked is None:
        return web.json_response({"error": "CRYPTO_NOT_CONFIGURED"}, status=503)
    token, token_label = picked
    user = _auth(request, settings)
    body = await request.json()
    plan_triplet = _plan_or_none(body)
    if plan_triplet is None:
        return web.json_response({"error": "UNKNOWN_PLAN"}, status=400)
    product, plan, cfg = plan_triplet
    title = _PRODUCT_TITLE[product]

    # Скидка первого дня (11.09.2026) — см. _first_day_discount_active.
    # Считаем от УЖЕ дисконтированной звёздной цены, чтобы доллар и звёзды
    # на одном плане не расходились по разным формулам округления.
    stars_price = cfg["stars_price"]
    if product == "guro_id" and plan == "monthly" and \
            _first_day_discount_active(request.app["main_storage"], user["id"]):
        stars_price = round(stars_price * (100 - FIRST_DAY_DISCOUNT_PCT) / 100)
    amount = round(stars_price * GC.STARS_TO_USD_RATE, 2)

    try:
        invoice = await GCR.create_invoice(
            token,
            asset=GC.CRYPTO_ASSET,
            amount=amount,
            description=f"{title} ({cfg['label'].lower()})",
            payload=f"{_PRODUCT_PAYLOAD_PREFIX[product]}:{plan}:{user['id']}",
            paid_btn_url=settings.community_invite_url,
        )
    except GCR.CryptoBotError:
        logger.exception("guro_id: не удалось создать crypto-инвойс (token=%s) для user_id=%s product=%s plan=%s",
                          token_label, user["id"], product, plan)
        return web.json_response({"error": "CRYPTO_INVOICE_FAILED"}, status=502)

    pay_url = invoice.get("pay_url") or invoice.get("bot_invoice_url") or invoice.get("mini_app_invoice_url")
    return web.json_response({"pay_url": pay_url, "invoice_id": invoice.get("invoice_id")})


async def handle_crypto_webhook(request: web.Request) -> web.Response:
    """CryptoBot шлёт сюда POST при оплате инвойса (настраивается в
    дашборде приложения, см. OPERATIONS.md). Подпись обязательна — без нее
    кто угодно мог бы дёрнуть этот адрес и активировать себе подписку
    бесплатно. Определяем продукт по префиксу payload (Фаза 3) —
    guro_id_subscription: / guro_id_recruiter_subscription:."""
    settings, storage = request.app["settings"], request.app["storage"]
    # 29.08.2026 — с двумя токенами (см. _pick_crypto_token) заранее не
    # известно, каким из них создан ИМЕННО этот инвойс (у каждого
    # приложения CryptoBot свой вебхук-URL в его собственном дашборде, но
    # оба указывают на этот же адрес) — подпись проверяем по очереди
    # обоими настроенными токенами, подходит хотя бы один — вебхук наш.
    tokens = [t for t in (settings.cryptobot_api_token_new, settings.cryptobot_api_token) if t]
    if not tokens:
        return web.Response(status=503)

    raw_body = await request.read()
    signature = request.headers.get("crypto-pay-api-signature", "")
    matched_token = next((t for t in tokens if GCR.verify_webhook_signature(t, raw_body, signature)), None)
    if matched_token is None:
        logger.warning("guro_id: crypto webhook с неверной подписью, игнорирую")
        return web.Response(status=403)
    # 29.08.2026 (владелец: "платёж на старый кошелёк — моя личная доля, в
    # статистике участвовать не должна") — старый токен матчнулся ПРИ
    # настроенном новом = это тот самый 1 из 6 в кольце, персональная доля
    # владельца. Подписка активируется как обычно (см. activate_
    # subscription ниже) — платящий получает полный доступ, флаг влияет
    # ТОЛЬКО на dashboard_stats().active_subscriptions.
    is_personal_cut = bool(settings.cryptobot_api_token_new) and matched_token == settings.cryptobot_api_token

    data = await request.json()
    if data.get("update_type") != "invoice_paid":
        return web.Response(status=200)

    invoice = data.get("payload") or {}
    payload_str = invoice.get("payload", "")
    product = next(
        (p for p, prefix in _PRODUCT_PAYLOAD_PREFIX.items() if payload_str.startswith(prefix + ":")), None,
    )
    if product is None:
        return web.Response(status=200)

    parts = payload_str.split(":")  # <prefix>:<plan>:<user_id>
    plan = parts[1] if len(parts) > 1 else "monthly"
    plans = _PRODUCT_PLANS[product]
    cfg = plans.get(plan, plans["monthly"])
    try:
        user_id = int(parts[2]) if len(parts) > 2 else None
    except ValueError:
        user_id = None
    if user_id is None:
        logger.warning("guro_id: crypto webhook без user_id в payload: %s", payload_str)
        return web.Response(status=200)

    if product == "recruiter":
        # personal_cut (11.09.2026) — та же личная доля владельца, что и у
        # базовой подписки (см. is_personal_cut выше), теперь учитывается
        # и здесь, а не только для guro_users.
        expires_at = storage.activate_recruiter_subscription(user_id, cfg["duration_days"], personal_cut=is_personal_cut)
        logger.info(
            "guro_id: подписка рекрутера активирована через крипту user_id=%s plan=%s до %s",
            user_id, plan, expires_at,
        )
        try:
            async with Bot(token=settings.bot_token) as bot:
                await bot.send_message(
                    user_id,
                    f"✅ Кабинет рекрутера GURO ID активирован до {expires_at[:10]} (оплата в крипте).",
                )
                await release_gated_message(bot, request.app["main_storage"], storage,
                                             settings.community_chat_id, user_id)
        except Exception:  # noqa: BLE001
            logger.exception("guro_id: не удалось уведомить о recruiter crypto-оплате user_id=%s", user_id)
        return web.Response(status=200)

    if product in _PRODUCT_COMPANY_TIER:
        tier = _PRODUCT_COMPANY_TIER[product]
        # personal_cut (11.09.2026) — см. комментарий у recruiter выше.
        expires_at = storage.activate_company_subscription(
            user_id, cfg["duration_days"], tier=tier, personal_cut=is_personal_cut,
        )
        logger.info(
            "guro_id: подписка компании (%s) активирована через крипту user_id=%s plan=%s до %s",
            tier, user_id, plan, expires_at,
        )
        try:
            async with Bot(token=settings.bot_token) as bot:
                await bot.send_message(
                    user_id,
                    f"✅ Кабинет компании GURO ID ({tier}) активирован до {expires_at[:10]} (оплата в крипте).",
                )
                await release_gated_message(bot, request.app["main_storage"], storage,
                                             settings.community_chat_id, user_id)
        except Exception:  # noqa: BLE001
            logger.exception("guro_id: не удалось уведомить о company crypto-оплате user_id=%s", user_id)
        return web.Response(status=200)

    expires_at = storage.activate_subscription(user_id, cfg["duration_days"], personal_cut=is_personal_cut)
    logger.info(
        "guro_id: подписка активирована через крипту user_id=%s plan=%s до %s",
        user_id, plan, expires_at,
    )
    try:
        async with Bot(token=settings.bot_token) as bot:
            await bot.send_message(
                user_id,
                f"✅ Подписка GURO ID активирована до {expires_at[:10]} (оплата в крипте) — "
                "полный поиск и просмотр профилей открыты.",
            )
            await GT.sync_member_tag(
                bot, settings.community_chat_id, storage, user_id,
                reason="subscription_activated_crypto",
            )
            await release_gated_message(bot, request.app["main_storage"], storage,
                                         settings.community_chat_id, user_id)
            # Платный вход в сообщество (09.09.2026): ссылка в группу —
            # только тем, кто пришёл через оплату. У старых участников
            # стоит признак «доступ без оплаты», они уже внутри.
            if not request.app["main_storage"].has_community_access(user_id):
                # Тексты через Content, а не из констант напрямую: владелец
                # правит их в CMS бота, и правка должна работать одинаково
                # при оплате звёздами и криптой.
                content = Content(request.app["main_storage"])
                await CA.grant_access(
                    bot, settings, user_id,
                    content.txt("paywall_granted"),
                    content.btn("join"), content.btn("guro_id"),
                )
    except Exception:  # noqa: BLE001
        logger.exception("guro_id: не удалось уведомить/обновить тег после crypto-оплаты user_id=%s", user_id)

    return web.Response(status=200)


def create_app(settings: Settings) -> web.Application:
    # client_max_size (28.08.2026) — aiohttp по умолчанию режет ЛЮБОЕ тело
    # запроса на 1 МБ, это МЕНЬШЕ, чем собственный лимит обложки компании
    # (5 МБ, см. COMPANY_UPLOAD_MAX_BYTES) — без явного увеличения реальные
    # фото с телефона (обычно 2-10 МБ) валились бы сырым 413 до того, как
    # наш код вообще успевал бы ответить понятным FILE_TOO_LARGE. Запас
    # сверх 5 МБ — под multipart-обвязку (имя поля, boundary и т.п.).
    app = web.Application(client_max_size=6 * 1024 * 1024)
    app["settings"] = settings
    app["storage"] = GuroStorage(settings.database_path)
    app["main_storage"] = Storage(settings.database_path)
    app.router.add_get("/api/me", handle_me)
    app.router.add_get("/api/search", handle_search)
    app.router.add_get("/api/candidates/count", handle_candidates_count)
    app.router.add_post("/api/partnerships", handle_create_partnership)
    app.router.add_get("/api/messages", handle_list_messages)
    app.router.add_get("/api/messages/with/{user_id}", handle_get_thread)
    app.router.add_post("/api/messages", handle_send_message)
    app.router.add_get("/api/plans", handle_get_plans)
    app.router.add_post("/api/register", handle_register)
    app.router.add_post("/api/subscribe", handle_subscribe)
    app.router.add_post("/api/subscribe/crypto", handle_subscribe_crypto)
    app.router.add_post("/api/crypto/webhook", handle_crypto_webhook)
    app.router.add_post("/api/privacy", handle_set_privacy)
    app.router.add_post("/api/profile", handle_set_profile_field)
    app.router.add_post("/api/anketa", handle_set_anketa_field)
    app.router.add_post("/api/work_status", handle_set_work_status)
    app.router.add_post("/api/recruiter/activity_status", handle_set_recruiter_activity_status)
    app.router.add_post("/api/cv/field", handle_set_cv_field)
    app.router.add_post("/api/cv/profession", handle_set_cv_profession)
    app.router.add_post("/api/cv/grade", handle_set_cv_grade)
    app.router.add_post("/api/cv/flag", handle_set_cv_flag)
    app.router.add_post("/api/cv/salary", handle_set_cv_salary)
    app.router.add_post("/api/cv/experience", handle_add_cv_experience)
    app.router.add_post("/api/cv/experience/{entry_id}/delete", handle_delete_cv_experience)
    app.router.add_post("/api/recruiter/profile", handle_set_recruiter_profile_field)
    app.router.add_post("/api/recruiter/privacy", handle_set_recruiter_privacy)
    app.router.add_post("/api/company/profile", handle_set_company_profile_field)
    app.router.add_post("/api/company/image", handle_upload_company_image)
    app.router.add_post("/api/recruiter/image", handle_upload_recruiter_image)
    app.router.add_post("/api/company/privacy", handle_set_company_privacy)
    app.router.add_post("/api/company/verification/request", handle_request_company_verification)
    # Роли и команда (ТЗ "Роли и управление командой", 27.08.2026).
    app.router.add_post("/api/company/create", handle_create_company)
    app.router.add_get("/api/company/name_check", handle_company_name_check)
    app.router.add_post("/api/company/join_request", handle_company_join_request)
    app.router.add_get("/api/company/team", handle_get_company_team)
    app.router.add_post("/api/company/team/requests/{request_id}/approve", handle_approve_join_request)
    app.router.add_post("/api/company/team/requests/{request_id}/reject", handle_reject_join_request)
    app.router.add_post("/api/company/team/members/{user_id}/remove", handle_remove_company_member)
    app.router.add_post("/api/company/team/members/{user_id}/transfer", handle_transfer_company_ownership)
    app.router.add_post("/api/company/address", handle_submit_company_address)
    app.router.add_get("/api/company/addresses", handle_list_company_addresses)
    app.router.add_post("/api/partnerships/{id}/rate", handle_submit_rating)
    app.router.add_post("/api/partnerships/{id}/rate/delete", handle_delete_rating)
    app.router.add_get("/api/partnerships/pending_ratings", handle_pending_ratings)
    app.router.add_get("/api/qr", handle_get_qr)
    app.router.add_get("/api/invite_link", handle_invite_link)
    app.router.add_get("/api/positions", handle_get_positions)
    app.router.add_get("/api/vacancies", handle_list_vacancies)
    app.router.add_get("/api/vacancies/mine", handle_my_vacancies)
    app.router.add_post("/api/vacancies", handle_create_vacancy)
    app.router.add_get("/api/vacancies/{vacancy_id}", handle_get_vacancy)
    app.router.add_post("/api/vacancies/{vacancy_id}/edit", handle_edit_vacancy)
    app.router.add_post("/api/vacancies/{vacancy_id}/bookmark", handle_bookmark_vacancy)
    app.router.add_post("/api/vacancies/{vacancy_id}/pause", handle_pause_vacancy)
    app.router.add_post("/api/vacancies/{vacancy_id}/resume", handle_resume_vacancy)
    app.router.add_post("/api/vacancies/{vacancy_id}/extend", handle_extend_vacancy)
    app.router.add_post("/api/vacancies/{vacancy_id}/close", handle_close_vacancy)
    app.router.add_post("/api/vacancies/{vacancy_id}/respond", handle_respond_vacancy)
    app.router.add_get("/api/vacancies/{vacancy_id}/responses", handle_list_vacancy_responses)
    app.router.add_get("/api/responses", handle_list_my_responses)
    app.router.add_post("/api/responses/{response_id}/status", handle_update_response_status)
    if WEBAPP_DIST.exists():
        # add_static не отдаёт index.html на "/" сам по себе (показал бы
        # листинг директории) — раздаём его явным роутом, остальное статикой.
        async def handle_index(request: web.Request) -> web.Response:
            return web.FileResponse(WEBAPP_DIST / "index.html")

        app.router.add_get("/", handle_index)
        app.router.add_static("/assets", WEBAPP_DIST / "assets", show_index=False)
    # /uploads — папка юзерских файлов, отдельно от webapp/dist (см.
    # COMPANY_UPLOADS_DIR выше): dist пересобирается и перезаливается на
    # каждый деплой фронтенда, класть туда чужие загрузки нельзя, потерялись
    # бы. mkdir тут же — чтобы add_static не падал на первом же старте,
    # когда папки ещё никто не создал загрузкой.
    COMPANY_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    app.router.add_static("/uploads/company", COMPANY_UPLOADS_DIR, show_index=False)
    RECRUITER_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    app.router.add_static("/uploads/recruiter", RECRUITER_UPLOADS_DIR, show_index=False)
    return app


def main() -> None:
    settings = Settings.from_env()
    port = settings.guro_id_api_port
    logger.info("GURO ID API starting on 127.0.0.1:%s (static=%s)", port, WEBAPP_DIST.exists())
    web.run_app(create_app(settings), host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
