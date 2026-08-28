"""Одноразовая миграция (28.08.2026): переводит show_name/show_company/
show_vertical/show_profession личного профиля с opt-in (default=0) на
opt-out (default=1) — см. макет "09 · Приватность", Untitled-12.

Эти 4 колонки уже существовали в проде с default=0 (старое opt-in
поведение) — новый DEFAULT в guro_storage.py._init касается только СВЕЖИХ
БД (ALTER TABLE ADD COLUMN не перезаписывает уже существующие колонки).
На проде эти 4 тумблера были НЕДОЛГО вообще без гейта (см. git-историю
_PRIVACY_FIELD_MAP, коммит "01 · Профиль (личный)") — то есть ПРЯМО СЕЙЧАС
каждый пользователь и так виден чужим независимо от значения колонки.
Эта миграция просто переводит хранимое значение в 1 для всех, у кого оно
сейчас 0 — сохраняя status quo ("все видны") в момент, когда гейт
возвращается в _apply_privacy.

Запуск: python3 migrate_privacy_opt_out_default.py [--dry-run]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "gambling_community.sqlite3"
FIELDS = ("show_name", "show_company", "show_vertical", "show_profession")


def main(dry_run: bool) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) AS n FROM guro_users").fetchone()["n"]
    print(f"guro_users: {total} строк")

    for field in FIELDS:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM guro_users WHERE {field}=0 OR {field} IS NULL").fetchone()
        print(f"  {field}: будет переведено {row['n']} из {total}")

    if not dry_run:
        for field in FIELDS:
            conn.execute(f"UPDATE guro_users SET {field}=1 WHERE {field}=0 OR {field} IS NULL")

    if dry_run:
        print("DRY RUN — ничего не записано, откатываю транзакцию")
        conn.rollback()
    else:
        conn.commit()
        print("Записано и закоммичено.")
    conn.close()


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
