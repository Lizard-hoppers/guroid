"""Одноразовая миграция (09.09.2026): освобождение нынешних участников от
платного входа в сообщество.

Владелец: «правило касается только новых участников, те 1000 кто уже прошёл
тоже не просим оплачивать». Помечаем всех, у кого анкета УЖЕ есть на момент
запуска, признаком community_access_granted=1 — для них ни платный экран,
ни выселение по истечении подписки не действуют никогда.

Запускать НАДО ДО выкатки платного входа. Иначе между выкаткой и миграцией
правило успеет задеть тех, кого обещано не трогать.

Скрипт идемпотентен: повторный запуск ничего не меняет, потому что помечает
только строки с 0.

Запуск: python3 migrate_grandfather.py [--dry-run]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "gambling_community.sqlite3"


def main(dry_run: bool) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(DISTINCT user_id) AS n FROM profiles").fetchone()["n"]
    already = conn.execute(
        "SELECT COUNT(DISTINCT user_id) AS n FROM profiles WHERE community_access_granted = 1"
    ).fetchone()["n"]
    to_mark = conn.execute(
        "SELECT COUNT(DISTINCT user_id) AS n FROM profiles "
        "WHERE community_access_granted = 0 OR community_access_granted IS NULL"
    ).fetchone()["n"]

    print(f"анкет всего: {total}")
    print(f"уже освобождены: {already}")
    print(f"будет освобождено: {to_mark}")

    if dry_run:
        print("\nСУХОЙ ПРОГОН, ничего не записано. Запусти без --dry-run.")
        return

    conn.execute(
        "UPDATE profiles SET community_access_granted = 1 "
        "WHERE community_access_granted = 0 OR community_access_granted IS NULL"
    )
    conn.commit()

    after = conn.execute(
        "SELECT COUNT(DISTINCT user_id) AS n FROM profiles WHERE community_access_granted = 1"
    ).fetchone()["n"]
    left = conn.execute(
        "SELECT COUNT(DISTINCT user_id) AS n FROM profiles "
        "WHERE community_access_granted = 0 OR community_access_granted IS NULL"
    ).fetchone()["n"]
    print(f"\nосвобождены: {after}")
    print(f"под платным входом осталось: {left} (должно быть 0 — новые появятся позже)")
    print("ГОТОВО")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
