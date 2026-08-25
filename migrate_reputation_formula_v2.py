"""Одноразовая миграция (25.08.2026): пересчитать ВСЮ историю партнёрств и
guro_users.reputation_score под формулу рейтинга v2 (ТЗ "Сделка, формула
рейтинга, анти-абьюз") — по прямому решению владельца (см. AskUserQuestion в
сессии 25.08.2026: "Пересчитать всю историю"). Заменяет линейную модель
15-16.08.2026 (см. migrate_reputation_reset.py — тот пересчёт тоже устарел).

Осознанные допущения (историю нельзя восстановить полностью честно):
- "Обе стороны с активной подпиской на момент подтверждения" (6, новое
  условие) — нет исторических снимков статуса подписки на КАЖДЫЙ момент
  сделки, только текущий срез. Для ИСТОРИЧЕСКИХ партнёрств учитывается
  только стаж (как в migrate_reputation_reset.py), БЕЗ проверки подписки —
  иначе задним числом обнулили бы сделки тех, кто был подписан тогда, но
  не подписан сейчас. Правило "обе подписаны" действует только для НОВЫХ
  подтверждений (см. guro_storage.respond_partnership).
- Крипто-хеш (5.4/5.5) — исторические tx_hash НЕ верифицируются повторно
  ончейн этой миграцией (ненадёжно и долго по сети разом на всей истории,
  вне скоупа одноразового скрипта) — bonus/company_match остаются False.
- Оценки Шага 2 (6.1) — фичи не существовало до этой сессии, у исторических
  партнёрств рейтингов нет физически, они не участвуют в rating_delta.
- Тип сделки — все исторические записи получили ptype='deal' автоматически
  (DEFAULT колонки при добавлении, см. guro_storage._init), типа не
  существовало на момент их создания.

Запуск: python3 migrate_reputation_formula_v2.py [--dry-run]
--dry-run считает и печатает repeat_index/base_weight/tenure-флаг БЕЗ
записи в БД — но НЕ показывает итоговый reputation_score (тот считается
storage.recompute_total_w поверх УЖЕ записанных base_weight, посчитать его
честно без записи было бы отдельным дублирующим куском логики)."""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guro_constants as GC
import guro_logic as GL
from guro_storage import GuroStorage

DB_PATH = Path(__file__).resolve().parent / "gambling_community.sqlite3"


def main(dry_run: bool) -> None:
    # Прогоняет мягкие миграции схемы (новые колонки ptype/repeat_index/
    # base_weight/total_w и т.д., см. GuroStorage._init) ПЕРЕД тем, как
    # читать их напрямую сырым sqlite3 — без этого шага колонок ещё нет
    # (проверено вживую: голый sqlite3.connect их не создаёт).
    GuroStorage(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc)

    users = conn.execute("SELECT user_id, reputation_score FROM guro_users").fetchall()
    print(f"guro_users: {len(users)} строк")

    partnerships = conn.execute(
        "SELECT * FROM partnerships WHERE status=? ORDER BY confirmed_at ASC",
        (GC.PARTNERSHIP_STATUS_CONFIRMED,),
    ).fetchall()
    print(f"подтверждённых партнёрств: {len(partnerships)}")

    profiles_created_at: dict[int, datetime | None] = {}

    def created_at(uid: int) -> datetime | None:
        if uid not in profiles_created_at:
            row = conn.execute("SELECT created_at FROM profiles WHERE user_id=?", (uid,)).fetchone()
            profiles_created_at[uid] = GL.parse_db_datetime(row["created_at"]) if row else None
        return profiles_created_at[uid]

    repeat_seen: dict[tuple[int, int], int] = {}
    updates: list[tuple[int, int, int, float]] = []  # (id, counts, repeat_index, base_weight)
    for p in partnerships:
        a, b = p["initiator_id"], p["confirmer_id"]
        tenure_ok = GL.counts_toward_rating(created_at(a), created_at(b), now)
        pair_key = (min(a, b), max(a, b))
        repeat_index = repeat_seen.get(pair_key, 0)
        base_weight = (
            GL.partnership_base_weight(p["ptype"] or GC.PARTNERSHIP_TYPE_DEAL, repeat_index)
            if tenure_ok else 0.0
        )
        updates.append((p["id"], 1 if tenure_ok else 0, repeat_index, base_weight))
        if tenure_ok:
            repeat_seen[pair_key] = repeat_index + 1

    print(f"будет обновлено строк partnerships: {len(updates)}")
    print("примеры (id, counts_toward_rating, repeat_index, base_weight):")
    for row in updates[:10]:
        print(" ", row)

    if dry_run:
        print("DRY RUN — ничего не записано (ни partnerships, ни reputation_score).")
        conn.close()
        return

    conn.executemany(
        "UPDATE partnerships SET counts_toward_rating=?, repeat_index=?, base_weight=? WHERE id=?",
        [(counts, ri, bw, pid) for pid, counts, ri, bw in updates],
    )
    conn.commit()
    conn.close()

    storage = GuroStorage(DB_PATH)
    changed = 0
    sample = []
    for u in users:
        uid, before = u["user_id"], u["reputation_score"]
        after = storage.recompute_total_w(uid)
        if round(before or 0.0, 1) != round(after, 1):
            changed += 1
            if len(sample) < 10:
                sample.append((uid, before, round(after, 1)))
    print(f"reputation_score изменился у {changed} из {len(users)}")
    print("примеры (user_id, было, стало):")
    for row in sample:
        print(" ", row)
    print("Записано и закоммичено.")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
