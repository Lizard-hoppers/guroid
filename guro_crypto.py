"""CryptoBot (Crypto Pay API) — приём оплаты подписки GURO ID в крипте
(USDT), альтернатива Telegram Stars. Тонкая обёртка над их REST API
(https://help.crypt.bot/crypto-pay-api), больше никакой логики тут нет.

Токен — CRYPTOBOT_API_TOKEN в .env. Получить: открыть @CryptoBot в
Telegram -> Crypto Pay -> My Apps -> Create App -> скопировать API-токен.
Без токена (settings.cryptobot_api_token пустой) крипто-эндпойнты в
guro_id_api.py отдают 503 — см. handle_subscribe_crypto/handle_crypto_webhook.
"""
from __future__ import annotations

import hashlib
import hmac
import logging

import aiohttp

logger = logging.getLogger(__name__)

API_BASE = "https://pay.crypt.bot/api"
_TIMEOUT = aiohttp.ClientTimeout(total=15)


class CryptoBotError(Exception):
    pass


async def create_invoice(
    api_token: str,
    *,
    asset: str,
    amount: float,
    description: str,
    payload: str,
    paid_btn_url: str | None = None,
) -> dict:
    body = {
        "asset": asset,
        "amount": str(amount),
        "description": description,
        "payload": payload,
    }
    if paid_btn_url:
        body["paid_btn_name"] = "openBot"
        body["paid_btn_url"] = paid_btn_url
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{API_BASE}/createInvoice",
            headers={"Crypto-Pay-API-Token": api_token},
            json=body,
            timeout=_TIMEOUT,
        ) as resp:
            data = await resp.json()
    if not data.get("ok"):
        raise CryptoBotError(f"createInvoice failed: {data}")
    return data["result"]


async def get_invoice(api_token: str, invoice_id: int) -> dict | None:
    """Резервный способ проверить статус (поллингом), если вебхук почему-то
    не долетел — сейчас нигде не вызывается, оставлено на будущее/для
    ручной проверки через шелл при разборе инцидентов."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{API_BASE}/getInvoices",
            headers={"Crypto-Pay-API-Token": api_token},
            params={"invoice_ids": str(invoice_id)},
            timeout=_TIMEOUT,
        ) as resp:
            data = await resp.json()
    if not data.get("ok"):
        return None
    items = data["result"]["items"]
    return items[0] if items else None


def verify_webhook_signature(api_token: str, body: bytes, signature: str) -> bool:
    """Подпись в заголовке `crypto-pay-api-signature` — hex HMAC-SHA256 от
    тела запроса, ключ — SHA256(api_token) (см. доку CryptoBot, раздел
    Webhooks). Без этой проверки кто угодно мог бы дёрнуть наш вебхук и
    активировать себе подписку бесплатно."""
    secret = hashlib.sha256(api_token.encode()).digest()
    computed = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)
