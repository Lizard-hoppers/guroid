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
import re
from dataclasses import dataclass
from datetime import datetime, timezone

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


# Извлечение хеша из вставленной ссылки на эксплорер (25.08.2026, фидбек
# владельца "Правки.pdf": "юзеру проще вставить ссылку на транзакцию, чем
# копировать хеш" — люди реально шлют друг другу именно ссылки вида
# tronscan.org/transaction/<hash>/overview). Каждый паттерн просто ищет
# ID-подобную подстроку после известного пути эксплорера — если ничего не
# совпало, считаем весь ввод уже голым хешем (см. extract_tx_hash).
# Сеть по домену эксплорера (ТЗ раздел 5): если человек вставил ссылку,
# незачем заставлять его ещё и выбирать сеть руками — она уже в ссылке.
_EXPLORER_NETWORKS = (
    ("tronscan.org", "tron"),
    ("etherscan.io", "ethereum"),
    ("bscscan.com", "bsc"),
)


def detect_network(raw: str) -> str | None:
    """Сеть из ссылки на эксплорер, иначе None (значит, выбирает человек)."""
    low = (raw or "").lower()
    for domain, network in _EXPLORER_NETWORKS:
        if domain in low:
            return network
    return None


_EXPLORER_URL_PATTERNS = (
    re.compile(r"tronscan\.org/(?:#/)?transaction/([0-9a-fA-F]{64})"),
    re.compile(r"etherscan\.io/tx/(0x[0-9a-fA-F]{64})"),
    re.compile(r"bscscan\.com/tx/(0x[0-9a-fA-F]{64})"),
)


def extract_tx_hash(raw: str) -> str:
    """Если raw — ссылка на известный эксплорер, вырезает из неё сам хеш
    (то, что реально нужно хранить/проверять — не URL целиком). Если
    ничего не совпало (уже голый хеш, или неизвестный формат ссылки) —
    возвращает вход как есть (обрезанный по краям)."""
    raw = (raw or "").strip()
    for pattern in _EXPLORER_URL_PATTERNS:
        match = pattern.search(raw)
        if match:
            return match.group(1)
    return raw


# Значения, которые приходят вместо хеша, когда что-то пошло не так на
# стороне клиента (str(None), JSON-строка "null" и т.п.).
_JUNK_HASHES = frozenset({"none", "null", "undefined", "nan"})


def normalize_tx_hash(raw: str) -> str:
    """Единый вид хеша для ХРАНЕНИЯ и СРАВНЕНИЯ (ТЗ «Hash_Uniqueness»,
    раздел 2): вырезать хеш из ссылки, обрезать края, привести к нижнему
    регистру. Хеши всех трёх поддерживаемых сетей шестнадцатеричные,
    поэтому регистр в них ничего не значит — а без приведения один и тот же
    перевод, вставленный ссылкой и голым хешем (или из разных источников с
    разным регистром), прошёл бы проверку уникальности как два разных."""
    normalized = extract_tx_hash(raw).lower()
    # Подделки под значение: так в базе однажды оказался хеш 'None' (см.
    # guro_id_api._body_text). Даже если такой мусор придёт не с нашего
    # фронта, принимать его за хеш нельзя — на нём висит и проверка
    # «сделка без хеша не заводится», и уникальность.
    return "" if normalized in _JUNK_HASHES else normalized


@dataclass
class VerifyResult:
    verified: bool
    from_address: str | None = None
    to_address: str | None = None
    amount: float | None = None  # в единицах актива (USDT), не в raw/wei
    error: str | None = None
    # Время транзакции в сети, UTC (ТЗ «Hash_Uniqueness», раздел 5) — нужно
    # для проверки давности. None, если эксплорер его не отдал: тогда
    # давность просто не проверяется, отсутствие даты не повод отказывать.
    timestamp: datetime | None = None


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


def _epoch_ms_to_dt(value) -> datetime | None:
    """Время эксплорера (мс от эпохи) -> datetime в UTC. Возвращает None на
    любом мусоре: дата нужна только для мягкой проверки давности, и её
    отсутствие не должно ронять верификацию."""
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


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

    # Tronscan отдаёт время прямо в ответе transaction-info, в мс.
    ts = _epoch_ms_to_dt(data.get("timestamp"))

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
            amount=amount, timestamp=ts,
        )

    # Нет токен-трансфера в логах -> нативный TRX перевод (contractData.amount, SUN, 1e6=1 TRX).
    contract_data = data.get("contractData") or {}
    raw_amount = contract_data.get("amount")
    return VerifyResult(
        True, from_address=data.get("ownerAddress"), to_address=data.get("toAddress"),
        amount=(raw_amount / 1_000_000) if isinstance(raw_amount, (int, float)) else None,
        timestamp=ts,
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

    # eth_getTransactionReceipt времени не содержит — только номер блока.
    # Спрашиваем время блока отдельно; не получилось — оставляем None,
    # проверка давности тогда просто не сработает (мягкий деграйд, как и
    # везде в этом модуле).
    block_ts = None
    block_number = result.get("blockNumber")
    if block_number:
        block, block_err = await _get_json(
            ETHERSCAN_V2_BASE,
            {"chainid": chain_id, "module": "proxy", "action": "eth_getBlockByNumber",
             "tag": block_number, "boolean": "false", "apikey": api_key},
        )
        raw_ts = (block or {}).get("result", {}).get("timestamp") if not block_err else None
        if isinstance(raw_ts, str):
            try:
                block_ts = datetime.fromtimestamp(int(raw_ts, 16), tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                block_ts = None

    from_addr, to_addr, amount = _decode_evm_transfer_log(result.get("logs") or [], network)
    if from_addr is None:
        # Нет ERC20/BEP20 Transfer-события в логах -> это НЕ токен-перевод
        # USDT (например голый ETH/BNB) — для нашего продукта (USDT-only,
        # см. GC.CRYPTO_ASSET) считаем неверифицированным, а не нативным
        # переводом (в отличие от Tron, где нативный TRX тоже принимается —
        # там это явный кейс из ТЗ-примера сетей, для EVM нативная монета
        # не является заявленным активом продукта).
        return VerifyResult(False, error="NO_TOKEN_TRANSFER")
    return VerifyResult(
        True, from_address=from_addr, to_address=to_addr, amount=amount, timestamp=block_ts,
    )


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
