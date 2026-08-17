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

import logging
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, WebAppInfo

import guro_constants as GC
import guro_crypto as GCR
import guro_logic as GL
import guro_tags as GT
from config import Settings
from guro_storage import GuroStorage
from storage import Storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("guro_id_api")

WEBAPP_DIST = Path(__file__).resolve().parent / "webapp" / "dist"


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

    partners = []
    for p in storage.list_confirmed_partnerships(user_id):
        other_id = p["confirmer_id"] if p["initiator_id"] == user_id else p["initiator_id"]
        other_profile = storage.get_profile(other_id)
        amount_visible = bool(p["amount_visible"])
        partners.append({
            "user_id": other_id,
            "username": other_profile["username"] if other_profile else None,
            "name": other_profile["name"] if other_profile else None,
            "confirmed_at": p["confirmed_at"],
            "counts_toward_rating": bool(p["counts_toward_rating"]),
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
            # Кто именно указал офер/суммы (со слов инициатора, не факт,
            # подтверждённый confirmer'ом) — фронту нужно, чтобы подписать
            # "получил/заплатил" с правильной стороны.
            "initiator_id": p["initiator_id"],
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
        "linkedin": profile["linkedin"],
        # "Что для вас сейчас актуально" из анкеты бота — семантически
        # ровно "Я ищу" из макета редизайна, отдельного поля не заводили.
        "looking_for": profile["request"],
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
        "confirmed_partnerships": storage.count_confirmed_partnerships(user_id),
        "partners": partners,
        "subscription_status": guro_user["subscription_status"],
        "subscription_expires_at": guro_user["subscription_expires_at"],
        "is_subscribed": storage.is_subscribed(user_id),
    }


# Поле профиля -> тумблер приватности, который его ПОКАЗЫВАЕТ. Opt-in:
# по умолчанию (флаг выключен) поле СКРЫТО, владелец сам включает то, что
# хочет показать чужим. Партнёрства (с кем сотрудничал) сюда намеренно не
# входят — тумблеры приватности их не трогают (это ядро смысла GURO ID),
# но их скрывает ДРУГОЙ, независимый механизм — подписка САМОГО владельца
# профиля, см. _apply_subscription_gate ниже.
_PRIVACY_FIELD_MAP = {
    "show_name": ("name",),
    "show_company": ("company",),
    "show_vertical": ("vertical",),
    "show_profession": ("profession",),
    "show_tenure": ("joined_community_at", "days_in_community"),
    "show_reputation": ("reputation_score",),
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
_SUBSCRIPTION_GATED_FIELDS = ("reputation_score", "confirmed_partnerships", "partners")


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


def _recruiter_summary(storage: GuroStorage, user_id: int) -> dict:
    """Кабинет рекрутера (Фаза 3, 12.08.2026) — САТЕЛЛИТ личного профиля,
    своя витрина + своя ОТДЕЛЬНАЯ подписка (рейтинг/партнёрства остаются
    общими, берутся из личного /api/me). is_recruiter_subscribed=False не
    404-ит (в отличие от NO_PROFILE у личного профиля) — фронт сам решает,
    показать апсейл или редактор, витрина технически "существует" с
    первого же запроса (get_or_create)."""
    row = storage.get_or_create_recruiter_profile(user_id)
    extra = storage.get_recruiter_extra(user_id)
    return {
        "workspace": "recruiter",
        "user_id": user_id,
        **extra,
        "recruiter_subscription_status": row["subscription_status"],
        "recruiter_subscription_expires_at": row["subscription_expires_at"],
        "is_recruiter_subscribed": storage.is_recruiter_subscribed(user_id),
    }


async def handle_me(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)

    if request.query.get("workspace") == "recruiter":
        summary = _recruiter_summary(storage, user["id"])
        summary["privacy"] = storage.get_recruiter_privacy(user["id"])
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
    try:
        await GT.sync_member_tag_standalone(
            settings.bot_token, settings.community_chat_id, storage, user["id"], reason="api_me",
        )
    except Exception:  # noqa: BLE001
        logger.exception("guro_id: tag sync failed for user %s", user["id"])
    return web.json_response(summary)


def _profile_response(storage: GuroStorage, requester_id: int, target_profile) -> dict:
    """Строит JSON для ОДНОГО профиля — полная карточка, если requester
    подписан, иначе урезанный бесплатный тизер (ТЗ экран 2). Общая логика
    для всех трёх режимов handle_search (user_id=/username=/точный матч
    внутри q=)."""
    privileged = requester_id in GC.PRIVILEGED_VIEWER_IDS
    summary = _profile_summary(storage, target_profile["user_id"])
    privacy = storage.get_privacy(target_profile["user_id"])
    summary = _apply_privacy(summary, privacy, bypass=privileged)
    # target'а (не смотрящего!) подписка гейтит рейтинг/сделки — «рейтинг
    # сгорает без подписки», см. _apply_subscription_gate.
    summary = _apply_subscription_gate(summary, summary["is_subscribed"], bypass=privileged)

    if storage.is_subscribed(requester_id):
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
    в точном поиске по юзернейму."""
    bypass = requester_id in GC.PRIVILEGED_VIEWER_IDS
    matches: list[tuple[int, dict]] = []
    for user_id in storage.list_guro_user_ids():
        if user_id == requester_id:
            continue  # сам себя в directory-режимах видеть незачем
        privacy = storage.get_privacy(user_id)
        if require_privacy_open and not bypass and not any(privacy.values()):
            continue  # ничего не открыто -> нечего показывать, не тратим время на профиль
        summary = _profile_summary(storage, user_id)
        if summary is None:
            continue
        summary = _apply_privacy(summary, privacy, bypass=bypass)
        summary = _apply_subscription_gate(summary, summary["is_subscribed"], bypass=bypass)
        score = match_fn(summary)
        if score > 0:
            matches.append((score, summary))
    return matches


def _rank_directory_matches(matches: list[tuple[int, dict]], *, top: bool) -> dict:
    """top=True («ТОП рейтинга», 11.08.2026) — чистая сортировка по
    репутации вместо силы совпадения (для browse по вертикали сила
    совпадения всегда одинакова, там top лишь один осмысленный порядок)."""
    if top:
        ranked = sorted(matches, key=lambda pair: pair[1].get("reputation_score") or 0, reverse=True)
    else:
        ranked = sorted(matches, key=lambda pair: (pair[0], pair[1].get("reputation_score") or 0), reverse=True)
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


def _directory_search(storage: GuroStorage, requester_id: int, query: str, *, top: bool) -> dict:
    """Поиск ПО ОПИСАНИЮ ("менеджер в крипто") — список всех, у кого есть
    совпадение среди полей, которые они САМИ открыли тумблерами
    приватности. Вызывается из handle_search, когда q= не совпал ни с
    одним точным юзернеймом (см. режимы ниже) — доступ уже проверен
    вызывающим (платная фича, 402 без подписки)."""
    keywords = query.lower().split()[: GC.DIRECTORY_QUERY_MAX_KEYWORDS]

    def match_fn(summary: dict) -> int:
        haystack = _searchable_text(summary)
        return sum(1 for kw in keywords if kw in haystack)

    matches = _scan_directory_candidates(storage, requester_id, match_fn)
    return _rank_directory_matches(matches, top=top)


def _directory_browse(storage: GuroStorage, requester_id: int, vertical: str, *, top: bool) -> dict:
    """Browse по вертикали (11.08.2026) — альтернатива текстовому поиску
    для тех, кто не знает точного юзернейма и не хочет формулировать
    запрос (см. PDF-фидбек владельца: "пока не понятно как они будут
    находить друг друга"). Сравнение — с КАНОНИЧЕСКИМ значением из
    constants.VERTICALS (то, что реально пишется в profiles.vertical при
    регистрации, см. handlers/flow.py), "Other" дополнительно матчит
    произвольные "Other: <текст>"."""
    vertical_lower = vertical.strip().lower()

    def match_fn(summary: dict) -> int:
        v = (summary.get("vertical") or "").lower()
        if v == vertical_lower:
            return 1
        if vertical_lower == "other" and v.startswith("other"):
            return 1
        return 0

    matches = _scan_directory_candidates(storage, requester_id, match_fn)
    return _rank_directory_matches(matches, top=top)


def _resume_browse(storage: GuroStorage, requester_id: int, vertical: str | None, *, top: bool) -> dict:
    """«Резюме» (Фаза 4, 12.08.2026) — не отдельный экран/эндпоинт, а
    доп. фильтр к тому же поиску: показывает только тех, кто отметил
    статус «Ищу работу» (work_status=looking), опционально ещё и по
    вертикали. require_privacy_open=False — см. _scan_directory_candidates."""
    vertical_lower = (vertical or "").strip().lower()

    def match_fn(summary: dict) -> int:
        if summary.get("work_status") != GC.WORK_STATUS_LOOKING:
            return 0
        if not vertical_lower:
            return 1
        v = (summary.get("vertical") or "").lower()
        if v == vertical_lower:
            return 1
        if vertical_lower == "other" and v.startswith("other"):
            return 1
        return 0

    matches = _scan_directory_candidates(storage, requester_id, match_fn, require_privacy_open=False)
    return _rank_directory_matches(matches, top=top)


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
    username = request.query.get("username", "")
    user_id_param = request.query.get("user_id", "")
    query = request.query.get("q", "")
    vertical = request.query.get("vertical", "").strip()
    top = request.query.get("top") == "1"
    resumes = request.query.get("resumes") == "1"

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

    if user_id_param:
        # Заход по QR (?target=<id> у Mini App, см. App.jsx) — ищем по ID,
        # не по юзернейму (тот мог смениться, ID стабилен).
        try:
            target_profile = storage.get_profile(int(user_id_param))
        except ValueError:
            target_profile = None
        if target_profile is None:
            return web.json_response({"error": "NOT_FOUND"}, status=404)
        return web.json_response(_profile_response(storage, requester["id"], target_profile))

    if username:
        target_profile = storage.find_profile_by_username(username)
        if target_profile is None:
            return web.json_response({"error": "NOT_FOUND"}, status=404)
        return web.json_response(_profile_response(storage, requester["id"], target_profile))

    if resumes:
        if not storage.is_subscribed(requester["id"]):
            return web.json_response({"error": "SUBSCRIPTION_REQUIRED"}, status=402)
        return web.json_response(_resume_browse(storage, requester["id"], vertical or None, top=top))

    if vertical:
        if not storage.is_subscribed(requester["id"]):
            return web.json_response({"error": "SUBSCRIPTION_REQUIRED"}, status=402)
        return web.json_response(_directory_browse(storage, requester["id"], vertical, top=top))

    q = query.strip()
    if not q:
        return web.json_response({"mode": "list", "results": [], "truncated": False})

    target_profile = storage.find_profile_by_username(q)
    if target_profile is not None:
        return web.json_response(_profile_response(storage, requester["id"], target_profile))

    # Не нашли точного юзернейма -> это описание, платный directory-поиск.
    if not storage.is_subscribed(requester["id"]):
        return web.json_response({"error": "SUBSCRIPTION_REQUIRED"}, status=402)
    return web.json_response(_directory_search(storage, requester["id"], q, top=top))


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
    offer = (str(body.get("offer", "")).strip()[:300]) or None
    review = (str(body.get("review", "")).strip()[:500]) or None
    amount_received = _parse_amount(body.get("amount_received"))
    amount_paid = _parse_amount(body.get("amount_paid"))
    amount_visible = bool(body.get("amount_visible"))
    # Хэш транзакции (16.08.2026) — 200 симв. с запасом покрывает любые
    # реальные хэши (Bitcoin/Ethereum/TRON и т.д. — все короче 100).
    tx_hash = (str(body.get("tx_hash", "")).strip()[:200]) or None

    target_profile = storage.find_profile_by_username(confirmer_username)
    if target_profile is None:
        return web.json_response({"error": "NO_CONFIRMER_PROFILE"}, status=404)

    try:
        partnership = storage.create_partnership(
            user["id"], target_profile["user_id"], vertical, geo,
            offer=offer, amount_received=amount_received, amount_paid=amount_paid,
            review=review, amount_visible=amount_visible, tx_hash=tx_hash,
        )
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=409)

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
            }
            for m in storage.list_messages(thread["id"])
        ]
        storage.mark_thread_read(thread["id"], user["id"])

    return web.json_response({
        "other_user_id": other_id,
        **_other_display(other_profile),
        "messages": messages,
        # Тред уже есть -> отвечать можно всегда; нового треда ещё нет ->
        # писать первым можно, только если СМОТРЯЩИЙ (сам user) подписан.
        "can_send_first": thread is not None or storage.is_subscribed(user["id"]),
    })


_MESSAGE_ERROR_STATUS = {
    "SELF_MESSAGE": 400,
    "EMPTY_BODY": 400,
    "NO_RECIPIENT_PROFILE": 404,
    "SUBSCRIPTION_REQUIRED": 402,
    "RATE_LIMITED": 429,
}


async def handle_send_message(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    text = str(body.get("body", ""))
    try:
        recipient_id = int(body.get("recipient_id"))
    except (TypeError, ValueError):
        return web.json_response({"error": "NO_RECIPIENT_PROFILE"}, status=404)

    try:
        message = storage.send_message(user["id"], recipient_id, text)
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


async def handle_set_profile_field(request: web.Request) -> web.Response:
    """Редактирование НОВЫХ полей профиля (GC.EXTRA_PROFILE_FIELDS: CV-текст,
    сайт, "чем полезен"). В отличие от полей анкеты (только чтение в Mini
    App, источник — бот), для этих полей другого способа заполнения нет,
    поэтому редактируются прямо здесь."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    field = str(body.get("field", ""))
    value = str(body.get("value", "")).strip()[:2000] or None
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
    value = str(body.get("value", "")).strip()[:2000] or None
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
    для этого нужна регистрация short name через @BotFather, которой нет."""
    settings = request.app["settings"]
    user = _auth(request, settings)
    deeplink = f"https://t.me/{settings.bot_username}?start={GC.QR_PAYLOAD_PREFIX}{user['id']}"
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


def _vacancy_public(storage: GuroStorage, row) -> dict:
    """Подмешивает компанию/имя автора из ЕГО кабинета рекрутера — вакансия
    сама по себе не хранит company, чтобы не дублировать данные, которые
    уже живут в guro_recruiter_profiles."""
    recruiter = storage.get_recruiter_extra(row["author_id"])
    return {
        "id": row["id"],
        "author_id": row["author_id"],
        "company": recruiter["company"],
        "recruiter_name": recruiter["name"],
        "title": row["title"],
        "vertical": row["vertical"],
        "seniority": row["seniority"],
        "location": row["location"],
        "remote": bool(row["remote"]),
        "relocation": bool(row["relocation"]),
        "salary_from": row["salary_from"],
        "salary_to": row["salary_to"],
        "salary_negotiable": bool(row["salary_negotiable"]),
        "description": row["description"],
        "lang": row["lang"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


async def handle_list_vacancies(request: web.Request) -> web.Response:
    """Просмотр доски — по БАЗОВОЙ подписке GURO ID (тот же пейволл, что и
    у остального поиска), публиковать может только подписчик кабинета
    рекрутера (см. handle_create_vacancy)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    if not storage.is_subscribed(user["id"]):
        return web.json_response({"error": "SUBSCRIPTION_REQUIRED"}, status=402)
    lang = request.query.get("lang") or None
    vertical = request.query.get("vertical") or None
    rows = storage.list_vacancies(lang=lang, vertical=vertical)
    return web.json_response({"vacancies": [_vacancy_public(storage, r) for r in rows]})


async def handle_my_vacancies(request: web.Request) -> web.Response:
    """Свои вакансии (включая закрытые) — для управления, доступно любому
    (даже если подписка рекрутера с тех пор истекла — старые публикации
    остаются видны владельцу для архивации)."""
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    rows = storage.list_my_vacancies(user["id"])
    return web.json_response({"vacancies": [_vacancy_public(storage, r) for r in rows]})


async def handle_create_vacancy(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    if not storage.is_recruiter_subscribed(user["id"]):
        return web.json_response({"error": "RECRUITER_SUBSCRIPTION_REQUIRED"}, status=402)
    body = await request.json()
    title = str(body.get("title", "")).strip()[: GC.VACANCY_TITLE_MAX]
    if not title:
        return web.json_response({"error": "TITLE_REQUIRED"}, status=400)
    lang = str(body.get("lang", "ru"))
    if lang not in GC.VACANCY_LANGS:
        lang = "ru"
    description = str(body.get("description", "")).strip()[: GC.VACANCY_DESCRIPTION_MAX] or None
    vacancy = storage.create_vacancy(
        user["id"],
        title=title,
        vertical=body.get("vertical") or None,
        seniority=body.get("seniority") or None,
        location=body.get("location") or None,
        remote=bool(body.get("remote")),
        relocation=bool(body.get("relocation")),
        salary_from=_parse_amount(body.get("salary_from")),
        salary_to=_parse_amount(body.get("salary_to")),
        salary_negotiable=bool(body.get("salary_negotiable")),
        description=description,
        lang=lang,
    )
    return web.json_response(_vacancy_public(storage, vacancy))


async def handle_close_vacancy(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    try:
        vacancy_id = int(request.match_info["vacancy_id"])
    except ValueError:
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    if not storage.close_vacancy(vacancy_id, user["id"]):
        return web.json_response({"error": "NOT_FOUND"}, status=404)
    return web.json_response({"status": "closed"})


# product -> тарифная сетка. Обобщено под ключ продукта (Фаза 3, 12.08.2026)
# вместо копипасты Stars+крипто-эндпоинтов под кабинет рекрутера — одна
# проверенная в проде платёжная цепочка на оба продукта.
_PRODUCT_PLANS = {"guro_id": GC.SUBSCRIPTION_PLANS, "recruiter": GC.RECRUITER_SUBSCRIPTION_PLANS}
_PRODUCT_PAYLOAD_PREFIX = {"guro_id": "guro_id_subscription", "recruiter": "guro_id_recruiter_subscription"}
_PRODUCT_TITLE = {"guro_id": "GURO ID — подписка", "recruiter": "GURO ID — кабинет рекрутера"}
_PRODUCT_DESCRIPTION = {
    "guro_id": "Полный поиск и просмотр профилей участников GURO ID: рейтинг, история партнёрств.",
    "recruiter": "Кабинет рекрутера GURO ID: отдельная витрина, публикация вакансий, просмотр резюме.",
}


def _plan_or_none(body: dict) -> tuple[str, str, dict] | None:
    product = str(body.get("product", "guro_id"))
    plans = _PRODUCT_PLANS.get(product)
    if plans is None:
        return None
    plan = str(body.get("plan", ""))
    cfg = plans.get(plan)
    return (product, plan, cfg) if cfg else None


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
    return web.json_response({"plans": plans, "crypto_enabled": bool(settings.cryptobot_api_token)})


async def handle_subscribe(request: web.Request) -> web.Response:
    settings = request.app["settings"]
    user = _auth(request, settings)
    body = await request.json()
    plan_triplet = _plan_or_none(body)
    if plan_triplet is None:
        return web.json_response({"error": "UNKNOWN_PLAN"}, status=400)
    product, plan, cfg = plan_triplet
    title = _PRODUCT_TITLE[product]

    bot = Bot(token=settings.bot_token)
    async with bot:
        link = await bot.create_invoice_link(
            title=f"{title} ({cfg['label'].lower()})",
            description=_PRODUCT_DESCRIPTION[product],
            payload=f"{_PRODUCT_PAYLOAD_PREFIX[product]}:{plan}:{user['id']}",
            provider_token=None,  # не нужен для Telegram Stars (Bot API 7.4+)
            currency="XTR",
            prices=[LabeledPrice(f"{title} — {cfg['label']}", cfg["stars_price"])],
        )
    return web.json_response({"invoice_link": link})


async def handle_subscribe_crypto(request: web.Request) -> web.Response:
    """Альтернатива Stars — оплата подписки в крипте через CryptoBot (Crypto
    Pay API). Подтверждение приходит асинхронно вебхуком (handle_crypto_
    webhook), а не сразу в ответе, в отличие от Stars-инвойса."""
    settings = request.app["settings"]
    if not settings.cryptobot_api_token:
        return web.json_response({"error": "CRYPTO_NOT_CONFIGURED"}, status=503)
    user = _auth(request, settings)
    body = await request.json()
    plan_triplet = _plan_or_none(body)
    if plan_triplet is None:
        return web.json_response({"error": "UNKNOWN_PLAN"}, status=400)
    product, plan, cfg = plan_triplet
    title = _PRODUCT_TITLE[product]
    amount = round(cfg["stars_price"] * GC.STARS_TO_USD_RATE, 2)

    try:
        invoice = await GCR.create_invoice(
            settings.cryptobot_api_token,
            asset=GC.CRYPTO_ASSET,
            amount=amount,
            description=f"{title} ({cfg['label'].lower()})",
            payload=f"{_PRODUCT_PAYLOAD_PREFIX[product]}:{plan}:{user['id']}",
            paid_btn_url=settings.community_invite_url,
        )
    except GCR.CryptoBotError:
        logger.exception("guro_id: не удалось создать crypto-инвойс для user_id=%s product=%s plan=%s",
                          user["id"], product, plan)
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
    if not settings.cryptobot_api_token:
        return web.Response(status=503)

    raw_body = await request.read()
    signature = request.headers.get("crypto-pay-api-signature", "")
    if not GCR.verify_webhook_signature(settings.cryptobot_api_token, raw_body, signature):
        logger.warning("guro_id: crypto webhook с неверной подписью, игнорирую")
        return web.Response(status=403)

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
        expires_at = storage.activate_recruiter_subscription(user_id, cfg["duration_days"])
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
        except Exception:  # noqa: BLE001
            logger.exception("guro_id: не удалось уведомить о recruiter crypto-оплате user_id=%s", user_id)
        return web.Response(status=200)

    expires_at = storage.activate_subscription(user_id, cfg["duration_days"])
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
    except Exception:  # noqa: BLE001
        logger.exception("guro_id: не удалось уведомить/обновить тег после crypto-оплаты user_id=%s", user_id)

    return web.Response(status=200)


def create_app(settings: Settings) -> web.Application:
    app = web.Application()
    app["settings"] = settings
    app["storage"] = GuroStorage(settings.database_path)
    app["main_storage"] = Storage(settings.database_path)
    app.router.add_get("/api/me", handle_me)
    app.router.add_get("/api/search", handle_search)
    app.router.add_post("/api/partnerships", handle_create_partnership)
    app.router.add_get("/api/messages", handle_list_messages)
    app.router.add_get("/api/messages/with/{user_id}", handle_get_thread)
    app.router.add_post("/api/messages", handle_send_message)
    app.router.add_get("/api/plans", handle_get_plans)
    app.router.add_post("/api/subscribe", handle_subscribe)
    app.router.add_post("/api/subscribe/crypto", handle_subscribe_crypto)
    app.router.add_post("/api/crypto/webhook", handle_crypto_webhook)
    app.router.add_post("/api/privacy", handle_set_privacy)
    app.router.add_post("/api/profile", handle_set_profile_field)
    app.router.add_post("/api/work_status", handle_set_work_status)
    app.router.add_post("/api/cv/field", handle_set_cv_field)
    app.router.add_post("/api/cv/profession", handle_set_cv_profession)
    app.router.add_post("/api/cv/grade", handle_set_cv_grade)
    app.router.add_post("/api/cv/flag", handle_set_cv_flag)
    app.router.add_post("/api/cv/salary", handle_set_cv_salary)
    app.router.add_post("/api/cv/experience", handle_add_cv_experience)
    app.router.add_post("/api/cv/experience/{entry_id}/delete", handle_delete_cv_experience)
    app.router.add_post("/api/recruiter/profile", handle_set_recruiter_profile_field)
    app.router.add_post("/api/recruiter/privacy", handle_set_recruiter_privacy)
    app.router.add_get("/api/qr", handle_get_qr)
    app.router.add_get("/api/invite_link", handle_invite_link)
    app.router.add_get("/api/vacancies", handle_list_vacancies)
    app.router.add_get("/api/vacancies/mine", handle_my_vacancies)
    app.router.add_post("/api/vacancies", handle_create_vacancy)
    app.router.add_post("/api/vacancies/{vacancy_id}/close", handle_close_vacancy)
    if WEBAPP_DIST.exists():
        # add_static не отдаёт index.html на "/" сам по себе (показал бы
        # листинг директории) — раздаём его явным роутом, остальное статикой.
        async def handle_index(request: web.Request) -> web.Response:
            return web.FileResponse(WEBAPP_DIST / "index.html")

        app.router.add_get("/", handle_index)
        app.router.add_static("/assets", WEBAPP_DIST / "assets", show_index=False)
    return app


def main() -> None:
    settings = Settings.from_env()
    port = settings.guro_id_api_port
    logger.info("GURO ID API starting on 127.0.0.1:%s (static=%s)", port, WEBAPP_DIST.exists())
    web.run_app(create_app(settings), host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
