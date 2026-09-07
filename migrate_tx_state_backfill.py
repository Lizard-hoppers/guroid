"""Одноразовая миграция (06.09.2026): приводит уже заведённые партнёрства
к трёхсостоянийной проверке из ТЗ «Верификация транзакций».

Строки заведены СТАРОЙ логикой, которая поднимала tx_verified по одному
факту, что транзакция найдена и не провалилась, — сумма не сверялась
вообще. Пока строки не переведены, старая ошибка продолжает действовать: на
tx_verified висит множитель рейтинга (см. guro_logic.rating_delta), то есть
человек получает бонус за перевод, которого в заявленном размере не было.

Рейтинг отдельно пересчитывать не нужно: recompute_total_w считает W с нуля
по текущему состоянию строк, поэтому достаточно поправить сам факт.

Заодно чистится мусор в поле хеша: у части строк там лежит СТРОКА "None"
(str(None) от прежней версии формы). Фронт считает её настоящим хешем и
рисует ссылку в эксплорер на несуществующую транзакцию.

Скрипт идемпотентен: повторный запуск ничего не меняет.

Запуск: python3 migrate_tx_state_backfill.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import guro_chain_verify as GCV
import guro_constants as GC
import guro_logic as GL
import guro_storage

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "gambling_community.sqlite3"
# Мусорные значения, которые в разное время попадали в поле хеша вместо
# самого хеша.
JUNK_HASHES = {"", "none", "null", "undefined"}


def read_api_keys() -> dict:
    """Читает из .env ТОЛЬКО три нужных ключа. Целиком .env не трогаем:
    там же лежат токены бота и строки подключения, и подтягивать их в
    окружение разового скрипта незачем."""
    wanted = {
        "TRONSCAN_API_KEY": "tron",
        "ETHERSCAN_API_KEY": "ethereum",
        "BSCSCAN_API_KEY": "bsc",
    }
    keys = {net: None for net in wanted.values()}
    env = BASE / ".env"
    if not env.exists():
        return keys
    for line in env.read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() in wanted:
            keys[wanted[name.strip()]] = value.strip() or None
    return keys


def main(dry_run: bool) -> None:
    storage = guro_storage.GuroStorage(str(DB_PATH))
    api_keys = read_api_keys()

    rows = storage._conn.execute(
        "SELECT id, initiator_id, confirmer_id, tx_hash, tx_network, tx_state, "
        "tx_verified, amount_received, amount_paid FROM partnerships"
    ).fetchall()
    if not rows:
        print("партнёрств нет, нечего переводить")
        return

    users = sorted({r["initiator_id"] for r in rows} | {r["confirmer_id"] for r in rows})
    before = {u: storage.recompute_total_w(u) for u in users}

    plan = []
    for r in rows:
        raw = (r["tx_hash"] or "").strip()
        if raw.lower() in JUNK_HASHES:
            plan.append((r["id"], f"мусор в поле хеша: {r['tx_hash']!r}", None, None, 0))
            continue

        declared = r["amount_received"] or r["amount_paid"] or None
        res = asyncio.run(GCV.verify_tx(r["tx_network"], raw, api_keys=api_keys))

        if res.verified and GL.amounts_match(declared, res.amount):
            state, verified = GC.TX_STATE_VERIFIED, 1
        elif res.verified and (declared is None or res.amount is None):
            # Сверять не с чем — «подтверждено» ставить нельзя.
            state, verified = GC.TX_STATE_NONE, 0
        elif res.verified or res.error in ("NOT_FOUND", "TX_FAILED"):
            state, verified = GC.TX_STATE_MISMATCH, 0
        else:
            # API недоступен, нет ключа, таймаут. Состояние не выдумываем,
            # но галочку снимаем: держать «подтверждено» без успешной сверки
            # нельзя ни при каких условиях (ТЗ раздел 4).
            state, verified = GC.TX_STATE_NONE, 0

        plan.append((
            r["id"],
            f"заявлено={declared} в сети={res.amount} ошибка={res.error}",
            state, res.amount, verified,
        ))

    for pid, note, state, amount, verified in plan:
        target = "чистим хеш" if state is None else f"состояние={state} tx_verified={verified}"
        print(f"#{pid}: {note} -> {target}")

    if dry_run:
        print("\nСУХОЙ ПРОГОН, ничего не записано.")
        return

    for pid, _note, state, amount, verified in plan:
        if state is None:
            storage._conn.execute(
                "UPDATE partnerships SET tx_hash=NULL, tx_network=NULL, tx_verified=0, "
                "tx_state=?, tx_amount=NULL WHERE id=?",
                (GC.TX_STATE_NONE, pid),
            )
        else:
            storage._conn.execute(
                "UPDATE partnerships SET tx_state=?, tx_amount=?, tx_verified=? WHERE id=?",
                (state, amount, verified, pid),
            )
    storage._conn.commit()

    after = {u: storage.recompute_total_w(u) for u in users}
    print("\nРейтинги (пересчитаны по новым фактам):")
    for u in users:
        mark = "" if abs(after[u] - before[u]) < 1e-9 else "  <- изменился"
        print(f"  {u}: {before[u]:.2f} -> {after[u]:.2f}{mark}")
    print("\nГОТОВО")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
