"""Чистые функции GURO ID: формула репутации, анти-фрод, валидация Telegram
WebApp initData. Без сайд-эффектов и без обращений к БД — ими занимается
guro_storage.py (тот же принцип разделения, что и в storage.py/logic.py)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

import guro_constants as GC

DATE_FMT = "%Y-%m-%d %H:%M:%S"  # формат created_at в existing storage.py


def parse_db_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, DATE_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def format_db_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(DATE_FMT)


def verify_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict | None:
    """Проверка подписи Telegram WebApp initData (см. core.telegram.org/bots/webapps
    #validating-data-received-via-the-mini-app). Возвращает распарсенный `user`
    из initData или None, если подпись/срок жизни не сошлись."""
    if not init_data:
        return None
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError:
        return None
    if auth_date <= 0 or (time.time() - auth_date) > max_age_seconds:
        return None

    user_raw = parsed.get("user")
    if not user_raw:
        return None
    try:
        user = json.loads(user_raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(user, dict) or "id" not in user:
        return None
    return user


def tenure_bonus(created_at: datetime | None, now: datetime) -> float:
    if created_at is None:
        return 0.0
    days = max(0, (now - created_at).days)
    periods = days // GC.TENURE_PERIOD_DAYS
    return min(GC.TENURE_BONUS_MAX, periods * GC.TENURE_BONUS_PER_PERIOD)


def initial_reputation(profile_created_at: datetime | None, now: datetime) -> float:
    """Стартовая репутация — дни в комьюнити (стаж) + подтверждённые сделки
    (16.08.2026, по официальному макету владельца, "рейтинг порядок.pdf":
    рейтинг состоит из этих двух составляющих — заменил устное решение
    днём раньше "рейтинг только от сделок"). Заполненная анкета сама по
    себе бонуса не даёт (дефолтное условие входа), стаж считается с даты
    регистрации."""
    return GC.BASE_REPUTATION + tenure_bonus(profile_created_at, now)


def confirmation_gain() -> float:
    """Вклад ОДНОГО подтверждённого партнёрства в рейтинг — фиксированный шаг
    (15.08.2026). Раньше зависел от репутации подтверждающего (вес × его_
    репутация / 100), но при старте рейтинга с нуля это ломало саму
    возможность стартовать — см. guro_constants.CONFIRMATION_GAIN."""
    return GC.CONFIRMATION_GAIN


def counts_toward_rating(a_created_at: datetime | None, b_created_at: datetime | None, now: datetime) -> bool:
    """False, если хотя бы один из пары младше MIN_TENURE_DAYS_TO_COUNT дней
    в комьюнити — партнёрство остаётся видимым, но не влияет на рейтинг."""
    for created_at in (a_created_at, b_created_at):
        if created_at is None:
            return False
        if (now - created_at).days < GC.MIN_TENURE_DAYS_TO_COUNT:
            return False
    return True


def rate_limited(last_request_at: datetime | None, now: datetime) -> bool:
    """True, если между той же парой уже была заявка младше RATE_LIMIT_HOURS."""
    if last_request_at is None:
        return False
    return (now - last_request_at) < timedelta(hours=GC.RATE_LIMIT_HOURS)


def subscription_expires_at(now: datetime, duration_days: int) -> datetime:
    return now + timedelta(days=duration_days)


def subscription_active(status: str | None, expires_at: datetime | None, now: datetime) -> bool:
    return status == GC.SUBSCRIPTION_ACTIVE and expires_at is not None and expires_at > now
