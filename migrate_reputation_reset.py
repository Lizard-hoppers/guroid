"""Одноразовая миграция (15.08.2026): пересчитать guro_users.reputation_score
с нуля под новую формулу (BASE_REPUTATION=0, CONFIRMATION_GAIN=1 за сделку,
вместо старой BASE=50 + пропорционального PageRank-подобного прироста).

Всё в ОДНОЙ транзакции (без промежуточных commit) — атомарно относительно
живого guro-id-api.service: любая параллельная запись от него либо целиком
до, либо целиком после этой миграции, без интерливинга.

Запуск: python3 migrate_reputation_reset.py [--dry-run]
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guro_constants as GC
import guro_logic as GL

DB_PATH = Path(__file__).resolve().parent / "gambling_community.sqlite3"


def main(dry_run: bool) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc)

    users = conn.execute("SELECT user_id FROM guro_users").fetchall()
    print(f"guro_users: {len(users)} строк")

    # Шаг 1: база для каждого — GL.initial_reputation(created_at, now).
    # 16.08.2026: бонус за стаж в комьюнити возвращён в формулу (был убран
    # 15.08 вечером, затем восстановлен по официальному макету владельца —
    # рейтинг = стаж + сделки), initial_reputation() снова принимает дату
    # регистрации.
    base_by_user: dict[int, float] = {}
    for u in users:
        profile = conn.execute(
            "SELECT created_at FROM profiles WHERE user_id=?", (u["user_id"],)
        ).fetchone()
        created_at = GL.parse_db_datetime(profile["created_at"]) if profile else None
        base_by_user[u["user_id"]] = GL.initial_reputation(created_at, now)

    # Шаг 2: +CONFIRMATION_GAIN за КАЖДОЕ подтверждённое учитываемое
    # партнёрство, каждой стороне — та же симметричная логика, что в
    # guro_storage.respond_partnership(), просто применённая разом по всей
    # истории вместо одной сделки за раз.
    partnerships = conn.execute(
        "SELECT initiator_id, confirmer_id FROM partnerships "
        "WHERE status=? AND counts_toward_rating=1",
        (GC.PARTNERSHIP_STATUS_CONFIRMED,),
    ).fetchall()
    print(f"учитываемых подтверждённых партнёрств: {len(partnerships)}")

    gain_by_user: dict[int, float] = {}
    for p in partnerships:
        gain_by_user[p["initiator_id"]] = gain_by_user.get(p["initiator_id"], 0.0) + GC.CONFIRMATION_GAIN
        gain_by_user[p["confirmer_id"]] = gain_by_user.get(p["confirmer_id"], 0.0) + GC.CONFIRMATION_GAIN

    changed = 0
    before_after_sample = []
    for u in users:
        uid = u["user_id"]
        new_score = base_by_user.get(uid, 0.0) + gain_by_user.get(uid, 0.0)
        old_score = conn.execute(
            "SELECT reputation_score FROM guro_users WHERE user_id=?", (uid,)
        ).fetchone()["reputation_score"]
        if old_score != new_score:
            changed += 1
            if len(before_after_sample) < 10:
                before_after_sample.append((uid, old_score, new_score))
            if not dry_run:
                conn.execute(
                    "UPDATE guro_users SET reputation_score=? WHERE user_id=?",
                    (new_score, uid),
                )

    print(f"изменится значений: {changed} из {len(users)}")
    print("примеры (user_id, было, стало):")
    for row in before_after_sample:
        print(" ", row)

    if dry_run:
        print("DRY RUN — ничего не записано, откатываю транзакцию")
        conn.rollback()
    else:
        conn.commit()
        print("Записано и закоммичено.")
    conn.close()


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
