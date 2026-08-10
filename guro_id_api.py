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
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice

import guro_constants as GC
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

    return {
        "user_id": user_id,
        "username": profile["username"],
        "name": profile["name"],
        "company": profile["company"],
        "vertical": profile["vertical"],
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


async def handle_me(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    user = _auth(request, settings)
    # Витрина разработчика — статичная карточка вместо профиля из БД (у автора
    # может не быть анкеты в этом конкретном боте), см. guro_showcase.py.
    if GS.is_showcase_username(user.get("username")):
        return web.json_response({**GS.PAYLOAD, "user_id": user["id"]})
    summary = _profile_summary(storage, user["id"])
    if summary is None:
        return web.json_response({"error": "NO_PROFILE"}, status=404)
    try:
        await GT.sync_member_tag_standalone(
            settings.bot_token, settings.community_chat_id, storage, user["id"], reason="api_me",
        )
    except Exception:  # noqa: BLE001
        logger.exception("guro_id: tag sync failed for user %s", user["id"])
    return web.json_response(summary)


async def handle_search(request: web.Request) -> web.Response:
    settings, storage = request.app["settings"], request.app["storage"]
    requester = _auth(request, settings)
    username = request.query.get("username", "")
    if GS.is_showcase_username(username):
        # Витрина видна ВСЕМ полностью, без пейволла — это самореклама, не
        # обычный профиль участника.
        return web.json_response(GS.PAYLOAD)
    target_profile = storage.find_profile_by_username(username)
    if target_profile is None:
        return web.json_response({"error": "NOT_FOUND"}, status=404)

    summary = _profile_summary(storage, target_profile["user_id"])
    if storage.is_subscribed(requester["id"]):
        summary["locked"] = False
        return web.json_response(summary)

    # Пейволл (ТЗ экран 2): без подписки — урезанная карточка.
    return web.json_response({
        "user_id": summary["user_id"],
        "username": summary["username"],
        "name": summary["name"],
        "reputation_score": summary["reputation_score"],
        "confirmed_partnerships": summary["confirmed_partnerships"],
        "locked": True,
    })


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


async def handle_subscribe(request: web.Request) -> web.Response:
    settings = request.app["settings"]
    user = _auth(request, settings)
    bot = Bot(token=settings.bot_token)
    async with bot:
        link = await bot.create_invoice_link(
            title="GURO ID — подписка на 30 дней",
            description="Полный поиск и просмотр профилей участников GURO ID: рейтинг, история партнёрств.",
            payload=f"guro_id_subscription:{user['id']}",
            provider_token=None,  # не нужен для Telegram Stars (Bot API 7.4+)
            currency="XTR",
            prices=[LabeledPrice("Подписка GURO ID, 30 дней", GC.SUBSCRIPTION_STARS_PRICE)],
        )
    return web.json_response({"invoice_link": link})


def create_app(settings: Settings) -> web.Application:
    app = web.Application()
    app["settings"] = settings
    app["storage"] = GuroStorage(settings.database_path)
    app.router.add_get("/api/me", handle_me)
    app.router.add_get("/api/search", handle_search)
    app.router.add_post("/api/partnerships", handle_create_partnership)
    app.router.add_post("/api/subscribe", handle_subscribe)
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
