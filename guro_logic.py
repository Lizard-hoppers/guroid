"""Чистые функции GURO ID: формула репутации, анти-фрод, валидация Telegram
WebApp initData. Без сайд-эффектов и без обращений к БД — ими занимается
guro_storage.py (тот же принцип разделения, что и в storage.py/logic.py)."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
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
    """5.6 — бонус за стаж в комьюнити, ЧАСТЬ W (не стартовая репутация,
    как было раньше) — +TENURE_BONUS_PER_DAY за каждый день, максимум
    TENURE_BONUS_MAX суммарно."""
    if created_at is None:
        return 0.0
    days = max(0, (now - created_at).days)
    return min(GC.TENURE_BONUS_MAX, days * GC.TENURE_BONUS_PER_DAY)


def reputation_from_w(w: float) -> float:
    """5.3 — сжатие суммы взвешенных очков (W) в шкалу 0-100. Быстрый рост на
    старте, замедление при большом W — объём не может "переиграть" систему."""
    return 100.0 * (1.0 - math.exp(-w / GC.REPUTATION_W_SCALE))


def reputation_tier(score: float) -> str:
    """Текстовый уровень (Bronze/Silver/Gold/Platinum) для быстрого
    визуального считывания рядом с числом — см. GC.REPUTATION_TIERS."""
    tier = GC.REPUTATION_TIERS[0][1]
    for threshold, label in GC.REPUTATION_TIERS:
        if score >= threshold:
            tier = label
    return tier


def repeat_decay_factor(repeat_index: int) -> float:
    """5.2 — 0 (первое партнёрство с этим контрагентом) -> 100%, 1..3-й
    повтор -> 20%, 4-й и далее повтор (repeat_index>=4) -> 0 (не считается,
    защита от фарма договорными сделками между двумя аккаунтами)."""
    if repeat_index <= 0:
        return 1.0
    if repeat_index < GC.PARTNERSHIP_REPEAT_MAX_COUNTED:
        return GC.PARTNERSHIP_REPEAT_DECAY
    return 0.0


def partnership_base_weight(ptype: str, repeat_index: int) -> float:
    """5.1+5.2 — очки ОДНОГО партнёрства без крипто-бонусов/штрафа (те
    применяются позже, при раскрытии оценки Шага 2, см. rating_delta).
    Это то, что добавляется в W сразу при подтверждении факта (Шаг 1)."""
    base = GC.PARTNERSHIP_BASE_POINTS.get(ptype, GC.PARTNERSHIP_BASE_POINTS[GC.PARTNERSHIP_TYPE_DEAL])
    return base * repeat_decay_factor(repeat_index)


def crypto_bonus_multiplier(verified: bool, company_match: bool) -> float:
    """5.4/5.5 — множитель к базовым очкам за верифицированный ончейн хеш;
    выше, если адрес совпал с верифицированным адресом компании (5.5,
    заменяет обычный множитель, не перемножается с ним)."""
    if not verified:
        return 1.0
    return GC.CRYPTO_COMPANY_MULTIPLIER if company_match else GC.CRYPTO_VERIFIED_MULTIPLIER


def log_amount_bonus(amount: float | None, *, tx_verified: bool) -> float:
    """5.4, последний пункт — логарифмическое сглаживание суммы. ДОПУЩЕНИЕ:
    применяется только при верифицированном ончейн хеше (см. комментарий у
    GC.CRYPTO_AMOUNT_LOG_COEFFICIENT) — без этого условия самозаявленная
    сумма была бы неограниченным вектором фарма рейтинга."""
    if not tx_verified or amount is None or amount <= 0:
        return 0.0
    return GC.CRYPTO_AMOUNT_LOG_COEFFICIENT * math.log10(1.0 + amount)


def rating_delta(
    verdict: str | None, base_weight: float, *, tx_verified: bool, tx_company_match: bool,
    amount: float | None,
) -> float:
    """6.1 "Влияние на рейтинг" — поправка к W ОДНОЙ стороны партнёрства,
    исходя из оценки, поставленной ЕЙ КОНТРАГЕНТОМ (не своей собственной).
    verdict=None — контрагент вообще не оценил (или оценка ещё не
    раскрыта) — эквивалентно "Были нюансы": базовые очки уже начислены при
    подтверждении (Шаг 1), бонусов/штрафа нет, нейтрально."""
    if verdict == GC.RATING_PROBLEMATIC:
        return -GC.PARTNERSHIP_PENALTY_POINTS
    if verdict == GC.RATING_SUCCESS:
        multiplier = crypto_bonus_multiplier(tx_verified, tx_company_match)
        bonus = base_weight * (multiplier - 1.0)
        bonus += log_amount_bonus(amount, tx_verified=tx_verified)
        return bonus
    return 0.0


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
