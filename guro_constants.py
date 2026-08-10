"""Константы модуля GURO ID (репутация/партнёрства). Отдельно от constants.py,
т.к. это самостоятельный модуль поверх старого функционала бота (см. ТЗ)."""
from __future__ import annotations

BASE_REPUTATION = 50.0

# Вес одного подтверждённого партнёрства в формуле репутации. Не зафиксирован
# в ТЗ — стартовое значение, настраивается по факту наблюдения за рейтингами.
CONFIRMATION_WEIGHT = 10.0

TENURE_BONUS_PER_PERIOD = 1.0
TENURE_PERIOD_DAYS = 90  # "каждые 3 мес"
TENURE_BONUS_MAX = 10.0

# Анти-фрод (ТЗ п.4): не больше 1 новой заявки в сутки на пару, и
# подтверждения между свежими (<14 дней в комьюнити) аккаунтами не
# учитываются в рейтинге (видны, но помечены).
RATE_LIMIT_HOURS = 24
MIN_TENURE_DAYS_TO_COUNT = 14

SUBSCRIPTION_DURATION_DAYS = 30
SUBSCRIPTION_STARS_PRICE = 150  # XTR, цена по факту согласования с владельцем

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

# Приватность (10.08.2026): владелец профиля решает в Mini App, что из
# анкеты видно чужим в поиске. Партнёрства (с кем сотрудничал) скрыть
# НЕЛЬЗЯ ни одним из тумблеров — это ядро смысла GURO ID (подтверждение
# репутации через сотрудничество), остаётся видно даже при максимальной
# приватности. hide_tenure прячет ОБА поля стажа разом (joined_community_at
# и days_in_community — это одно и то же для пользователя).
PRIVACY_FIELDS = ("hide_name", "hide_company", "hide_vertical", "hide_tenure", "hide_reputation")
