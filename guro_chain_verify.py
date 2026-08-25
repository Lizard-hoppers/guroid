"""Ончейн-верификация крипто-хеша сделки для GURO ID (ТЗ 5.4/5.5,
25.08.2026). НЕ платёжный модуль — для оплаты подписки см. guro_crypto.py
(CryptoBot); это подтверждение РЕАЛЬНОСТИ уже совершённого перевода МЕЖДУ
УЧАСТНИКАМИ сделки, дающее бонусный множитель к рейтингу (см. guro_logic.
crypto_bonus_multiplier/log_amount_bonus), проверяется при создании
партнёрства (guro_id_api.handle_create_partnership).

Сети (GC.TX_NETWORKS): tron/ethereum/bsc. Продукт работает с USDT (см.
GC.CRYPTO_ASSET) — токен-трансфер (TRC20/ERC20/BEP20), не нативный
TRX/ETH/BNB, поэтому парсим именно журнал/поле токен-трансфера, не
value самой транзакции.

Ключи: TRONSCAN_API_KEY (необязателен — публичный эндпойнт работает и без
него, ключ только поднимает рейт-лимит), ETHERSCAN_API_KEY/BSCSCAN_API_KEY
(ОБЯЗАТЕЛЬНЫ у Etherscan V2 unified API — без ключа верификация для этой
сети возвращает verified=False, reason=API_KEY_MISSING, тот же мягкий
деграйд, что у guro_crypto.py без CRYPTOBOT_API_TOKEN). Все три ключа
читаются из .env (см. config.Settings) и передаются вызывающим кодом.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=10)

TRONSCAN_BASE = "https://apilist.tronscanapi.com/api"
ETHERSCAN_V2_BASE = "https://api.etherscan.io/v2/api"
# Etherscan V2 unified API — один и тот же хост, сеть выбирается chainid.
_EVM_CHAIN_IDS = {"ethereum": 1, "bsc": 56}

# keccak256("Transfer(address,address,uint256)") — топик ERC20/BEP20-события
# Transfer в логах транзакции, единственный надёжный способ узнать
# реального отправителя/получателя/сумму ТОКЕНА (value самой tx у
# токен-переводов всегда 0 — движение денег идёт через call data/логи).
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# USDT decimals различаются по сети (десятичные знаки контракта, НЕ
# конфигурируемы) — ETH/TRON=6, Binance-Peg BSC-USD=18. Захардкожено,
# т.к. продукт работает только с USDT (GC.CRYPTO_ASSET) — если появится
# другой актив, тут понадобится реальный запрос decimals контракта.
_USDT_DECIMALS = {"tron": 6, "ethereum": 6, "bsc": 18}


@dataclass
class VerifyResult:
    verified: bool
    from_address: str | None = None
    to_address: str | None = None
    amount: float | None = None  # в единицах актива (USDT), не в raw/wei
    error: str | None = None


async def _get_json(url: str, params: dict) -> tuple[dict | None, str | None]:
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None, f"HTTP_{resp.status}"
                return await resp.json(), None
    except Exception:  # noqa: BLE001
        logger.exception("guro_chain_verify: сетевая ошибка запроса к %s", url)
        return None, "NETWORK_ERROR"


async def _verify_tron(tx_hash: str, api_key: str | None) -> VerifyResult:
    params = {"hash": tx_hash}
    headers = {}
    # Публичный эндпойнт работает и без ключа (проверено вживую 25.08.2026);
    # ключ, если есть, просто снимает часть рейт-лимита.
    if api_key:
        headers["TRON-PRO-API-KEY"] = api_key
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(f"{TRONSCAN_BASE}/transaction-info", params=params, headers=headers) as resp:
                if resp.status != 200:
                    return VerifyResult(False, error=f"HTTP_{resp.status}")
                data = await resp.json()
    except Exception:  # noqa: BLE001
        logger.exception("guro_chain_verify: сетевая ошибка Tronscan")
        return VerifyResult(False, error="NETWORK_ERROR")

    if not data or not data.get("hash"):
        return VerifyResult(False, error="NOT_FOUND")
    if data.get("contractRet") != "SUCCESS" or data.get("revert"):
        return VerifyResult(False, error="TX_FAILED")

    trc20 = data.get("trc20TransferInfo") or []
    if trc20:
        transfer = trc20[0]
        decimals = transfer.get("decimals", _USDT_DECIMALS["tron"])
        try:
            amount = int(transfer["amount_str"]) / (10 ** decimals)
        except (KeyError, TypeError, ValueError):
            amount = None
        return VerifyResult(
            True, from_address=transfer.get("from_address"), to_address=transfer.get("to_address"),
            amount=amount,
        )

    # Нет токен-трансфера в логах -> нативный TRX перевод (contractData.amount, SUN, 1e6=1 TRX).
    contract_data = data.get("contractData") or {}
    raw_amount = contract_data.get("amount")
    return VerifyResult(
        True, from_address=data.get("ownerAddress"), to_address=data.get("toAddress"),
        amount=(raw_amount / 1_000_000) if isinstance(raw_amount, (int, float)) else None,
    )


def _decode_evm_transfer_log(logs: list[dict], network: str) -> tuple[str | None, str | None, float | None]:
    for log in logs:
        topics = log.get("topics") or []
        if not topics or topics[0].lower() != _TRANSFER_TOPIC:
            continue
        if len(topics) < 3:
            continue
        from_addr = "0x" + topics[1][-40:]
        to_addr = "0x" + topics[2][-40:]
        try:
            raw = int(log.get("data", "0x0"), 16)
        except ValueError:
            raw = None
        amount = raw / (10 ** _USDT_DECIMALS[network]) if raw is not None else None
        return from_addr, to_addr, amount
    return None, None, None


async def _verify_evm(network: str, tx_hash: str, api_key: str | None) -> VerifyResult:
    if not api_key:
        return VerifyResult(False, error="API_KEY_MISSING")
    chain_id = _EVM_CHAIN_IDS[network]
    receipt, err = await _get_json(
        ETHERSCAN_V2_BASE,
        {"chainid": chain_id, "module": "proxy", "action": "eth_getTransactionReceipt",
         "txhash": tx_hash, "apikey": api_key},
    )
    if err:
        return VerifyResult(False, error=err)
    result = receipt.get("result") if receipt else None
    if not result:
        return VerifyResult(False, error="NOT_FOUND")
    if result.get("status") != "0x1":
        return VerifyResult(False, error="TX_FAILED")

    from_addr, to_addr, amount = _decode_evm_transfer_log(result.get("logs") or [], network)
    if from_addr is None:
        # Нет ERC20/BEP20 Transfer-события в логах -> это НЕ токен-перевод
        # USDT (например голый ETH/BNB) — для нашего продукта (USDT-only,
        # см. GC.CRYPTO_ASSET) считаем неверифицированным, а не нативным
        # переводом (в отличие от Tron, где нативный TRX тоже принимается —
        # там это явный кейс из ТЗ-примера сетей, для EVM нативная монета
        # не является заявленным активом продукта).
        return VerifyResult(False, error="NO_TOKEN_TRANSFER")
    return VerifyResult(True, from_address=from_addr, to_address=to_addr, amount=amount)


async def verify_tx(network: str, tx_hash: str, *, api_keys: dict[str, str | None]) -> VerifyResult:
    """api_keys — {"tron": ..., "ethereum": ..., "bsc": ...} (см.
    config.Settings.tronscan_api_key/etherscan_api_key/bscscan_api_key)."""
    tx_hash = (tx_hash or "").strip()
    if not tx_hash:
        return VerifyResult(False, error="EMPTY_HASH")
    if network == "tron":
        return await _verify_tron(tx_hash, api_keys.get("tron"))
    if network in _EVM_CHAIN_IDS:
        return await _verify_evm(network, tx_hash, api_keys.get(network))
    return VerifyResult(False, error="UNSUPPORTED_NETWORK")


def matches_company_address(result: VerifyResult, network: str, verified_addresses: set[tuple[str, str]]) -> bool:
    """5.5 — совпадает ли from ИЛИ to транзакции с адресом, верифицированным
    за компанией (guro_storage.verified_company_addresses(), тот же формат
    нормализации — lower())."""
    if not result.verified:
        return False
    for addr in (result.from_address, result.to_address):
        if addr and (network, addr.lower()) in verified_addresses:
            return True
    return False
