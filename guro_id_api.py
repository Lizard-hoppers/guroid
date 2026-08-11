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
import guro_showcase as GS
import guro_tags as GT
from config import Settings
from guro_storage import GuroStorage

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
        partners.append({
            "user_id": other_id,
            "username": other_profile["username"] if other_profile else None,
            "name": other_profile["name"] if other_profile else None,
            "confirmed_at": p["confirmed_at"],
            "counts_toward_rating": bool(p["counts_toward_rating"]),
        })

    extra = storage.get_extra_profile(user_id)
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
    "show_cv": ("cv_text",),
    "show_contacts": ("linkedin", "website"),
    "show_offers": ("looking_for", "offering"),
}


def _apply_privacy(summary: dict, privacy: dict) -> dict:
    """Заменяет на None поля карточки ЧУЖОГО профиля, которые владелец НЕ
    включил в своих настройках (ключ остаётся — фронту проще проверять
    `=== null`, чем угадывать отсутствие ключа). Opt-in: поле видно, только
    если соответствующий тумблер явно включён. На собственный `/api/me` не
    вызывается — там нужен полный набор данных плюс сами настройки, см.
    handle_me."""
    result = dict(summary)
    for flag, fields in _PRIVACY_FIELD_MAP.items():
        if not privacy.get(flag):
            for field in fields:
                result[field] = None
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


def _apply_subscription_gate(summary: dict, is_subscribed: bool) -> dict:
    if is_subscribed:
        return summary
    result = dict(summary)
    for field in _SUBSCRIPTION_GATED_FIELDS:
        result[field] = None if field != "partners" else []
    return result


async def handle_me(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    # Витрина разработчика — статичная карточка вместо профиля из БД (у автора
    # может не быть анкеты в этом конкретном боте), см. guro_showcase.py.
    # Приватность — исключение: это НАСТРОЙКИ САМОГО аккаунта, а не данные из
    # анкеты, они существуют независимо от того, показываем ли мы витрину
    # вместо обычного профиля. Без этого автор физически не может увидеть
    # свои тумблеры — витрина рендерится ВМЕСТО экрана с ними.
    if GS.is_showcase_username(user.get("username")):
        return web.json_response(
            {
                **GS.PAYLOAD, "user_id": user["id"], "privacy": storage.get_privacy(user["id"]),
                "unread_messages": storage.count_unread_messages(user["id"]),
            }
        )
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
    summary = _profile_summary(storage, target_profile["user_id"])
    privacy = storage.get_privacy(target_profile["user_id"])
    summary = _apply_privacy(summary, privacy)
    # target'а (не смотрящего!) подписка гейтит рейтинг/сделки — «рейтинг
    # сгорает без подписки», см. _apply_subscription_gate.
    summary = _apply_subscription_gate(summary, summary["is_subscribed"])

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


# Поля, участвующие в directory-поиске по описанию (10.08.2026) — только
# "описательные" текстовые поля профиля. Осознанно НЕ включены: linkedin/
# website (это URL, не то, что ищут по смыслу), joined_community_at/
# days_in_community/reputation_score (числа/даты, не текст). Порядок не
# важен — просто склеиваются в один "поисковый слепок".
_DIRECTORY_TEXT_FIELDS = ("name", "company", "vertical", "profession", "cv_text", "looking_for", "offering")


def _searchable_text(summary: dict) -> str:
    return " ".join(str(summary.get(f) or "") for f in _DIRECTORY_TEXT_FIELDS).lower()


def _directory_search(storage: GuroStorage, requester_id: int, query: str) -> dict:
    """Поиск ПО ОПИСАНИЮ ("менеджер в крипто") — список всех, у кого есть
    совпадение среди полей, которые они САМИ открыли тумблерами
    приватности. Вызывается из handle_search, когда q= не совпал ни с
    одним точным юзернеймом (см. режимы ниже) — доступ уже проверен
    вызывающим (платная фича, 402 без подписки)."""
    keywords = query.lower().split()[: GC.DIRECTORY_QUERY_MAX_KEYWORDS]
    matches: list[tuple[int, dict]] = []
    for user_id in storage.list_guro_user_ids():
        if user_id == requester_id:
            continue  # сам себя в directory-поиске видеть незачем
        privacy = storage.get_privacy(user_id)
        if not any(privacy.values()):
            continue  # ничего не открыто -> нечего искать, не тратим время на профиль
        summary = _profile_summary(storage, user_id)
        if summary is None:
            continue
        summary = _apply_privacy(summary, privacy)
        summary = _apply_subscription_gate(summary, summary["is_subscribed"])
        haystack = _searchable_text(summary)
        score = sum(1 for kw in keywords if kw in haystack)
        if score > 0:
            matches.append((score, summary))

    matches.sort(key=lambda pair: (pair[0], pair[1].get("reputation_score") or 0), reverse=True)
    top = matches[: GC.DIRECTORY_RESULTS_LIMIT]
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
        for _, s in top
    ]
    return {"mode": "list", "results": results, "truncated": len(matches) > len(top)}


async def handle_search(request: web.Request) -> web.Response:
    """Три режима запроса:
    - `user_id=<id>` — точный переход по ID (QR, клик по результату поиска).
    - `username=<name>` — точный переход по юзернейму (внутреннее использование).
    - `q=<текст>` — УНИВЕРСАЛЬНЫЙ поиск (10.08.2026, единственный режим,
      доступный из формы поиска фронта): сперва пробуем точный юзернейм
      (бесплатный тизер, как раньше) — не нашли, значит это уже описание,
      платный directory-поиск по открытым полям (см. _directory_search)."""
    settings, storage = request.app["settings"], request.app["storage"]
    requester = _auth(request, settings)
    username = request.query.get("username", "")
    user_id_param = request.query.get("user_id", "")
    query = request.query.get("q", "")

    if GS.is_showcase_username(username or query):
        # Витрина видна ВСЕМ полностью, без пейволла — это самореклама, не
        # обычный профиль участника.
        return web.json_response({**GS.PAYLOAD, "mode": "profile"})

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

    q = query.strip()
    if not q:
        return web.json_response({"mode": "list", "results": [], "truncated": False})

    target_profile = storage.find_profile_by_username(q)
    if target_profile is not None:
        return web.json_response(_profile_response(storage, requester["id"], target_profile))

    # Не нашли точного юзернейма -> это описание, платный directory-поиск.
    if not storage.is_subscribed(requester["id"]):
        return web.json_response({"error": "SUBSCRIPTION_REQUIRED"}, status=402)
    return web.json_response(_directory_search(storage, requester["id"], q))


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


async def handle_create_partnership(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    body = await request.json()
    confirmer_username = str(body.get("confirmer_username", "")).strip()
    vertical = body.get("vertical") or None
    geo = body.get("geo") or None

    target_profile = storage.find_profile_by_username(confirmer_username)
    if target_profile is None:
        return web.json_response({"error": "NO_CONFIRMER_PROFILE"}, status=404)

    try:
        partnership = storage.create_partnership(user["id"], target_profile["user_id"], vertical, geo)
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


async def handle_get_qr(request: web.Request) -> web.Response:
    """Deep-link на /start бота с payload guro_<user_id> — сканирующий
    получает от бота сообщение с web_app-кнопкой на Mini App с этим
    профилем (см. handlers/flow.py::start). Не прямая ссылка на Mini App —
    для этого нужна регистрация short name через @BotFather, которой нет."""
    settings = request.app["settings"]
    user = _auth(request, settings)
    deeplink = f"https://t.me/{settings.bot_username}?start={GC.QR_PAYLOAD_PREFIX}{user['id']}"
    return web.json_response({"deeplink": deeplink})


def _plan_or_none(body: dict) -> tuple[str, dict] | None:
    plan = str(body.get("plan", ""))
    cfg = GC.SUBSCRIPTION_PLANS.get(plan)
    return (plan, cfg) if cfg else None


async def handle_get_plans(request: web.Request) -> web.Response:
    """Единый источник цен для фронта (Stars + крипто-эквивалент) — чтобы
    числа в UI никогда не разъезжались с тем, что реально спишут.
    crypto_enabled=False, пока владелец не пропишет CRYPTOBOT_API_TOKEN —
    фронт по этому флагу прячет кнопку крипто-оплаты, а не бьётся в 503."""
    settings = request.app["settings"]
    plans = {}
    for key, cfg in GC.SUBSCRIPTION_PLANS.items():
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
    plan_pair = _plan_or_none(body)
    if plan_pair is None:
        return web.json_response({"error": "UNKNOWN_PLAN"}, status=400)
    plan, cfg = plan_pair

    bot = Bot(token=settings.bot_token)
    async with bot:
        link = await bot.create_invoice_link(
            title=f"GURO ID — подписка ({cfg['label'].lower()})",
            description="Полный поиск и просмотр профилей участников GURO ID: рейтинг, история партнёрств.",
            payload=f"guro_id_subscription:{plan}:{user['id']}",
            provider_token=None,  # не нужен для Telegram Stars (Bot API 7.4+)
            currency="XTR",
            prices=[LabeledPrice(f"Подписка GURO ID — {cfg['label']}", cfg["stars_price"])],
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
    plan_pair = _plan_or_none(body)
    if plan_pair is None:
        return web.json_response({"error": "UNKNOWN_PLAN"}, status=400)
    plan, cfg = plan_pair
    amount = round(cfg["stars_price"] * GC.STARS_TO_USD_RATE, 2)

    try:
        invoice = await GCR.create_invoice(
            settings.cryptobot_api_token,
            asset=GC.CRYPTO_ASSET,
            amount=amount,
            description=f"GURO ID — подписка ({cfg['label'].lower()})",
            payload=f"guro_id_subscription:{plan}:{user['id']}",
            paid_btn_url=settings.community_invite_url,
        )
    except GCR.CryptoBotError:
        logger.exception("guro_id: не удалось создать crypto-инвойс для user_id=%s plan=%s", user["id"], plan)
        return web.json_response({"error": "CRYPTO_INVOICE_FAILED"}, status=502)

    pay_url = invoice.get("pay_url") or invoice.get("bot_invoice_url") or invoice.get("mini_app_invoice_url")
    return web.json_response({"pay_url": pay_url, "invoice_id": invoice.get("invoice_id")})


async def handle_crypto_webhook(request: web.Request) -> web.Response:
    """CryptoBot шлёт сюда POST при оплате инвойса (настраивается в
    дашборде приложения, см. OPERATIONS.md). Подпись обязательна — без нее
    кто угодно мог бы дёрнуть этот адрес и активировать себе подписку
    бесплатно."""
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
    if not payload_str.startswith("guro_id_subscription:"):
        return web.Response(status=200)

    parts = payload_str.split(":")  # guro_id_subscription:<plan>:<user_id>
    plan = parts[1] if len(parts) > 1 else "monthly"
    cfg = GC.SUBSCRIPTION_PLANS.get(plan, GC.SUBSCRIPTION_PLANS["monthly"])
    try:
        user_id = int(parts[2]) if len(parts) > 2 else None
    except ValueError:
        user_id = None
    if user_id is None:
        logger.warning("guro_id: crypto webhook без user_id в payload: %s", payload_str)
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
    app.router.add_get("/api/qr", handle_get_qr)
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
