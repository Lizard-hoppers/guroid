"""Одноразовая миграция (06.09.2026): включает тумблеры видимости кабинета
«Компания» у уже существующих строк — «компания.pdf», стр. 3: «там, где
приватность, включить все тумблеры по умолчанию».

То же самое и по той же причине, что накануне сделано для кабинета
рекрутера (migrate_recruiter_privacy_default.py): колонки уже существуют в
проде со старым default=0, а новый DEFAULT в guro_storage.py._init
действует только на свежие БД.

ОСОЗНАННОЕ ДОПУЩЕНИЕ: переводим ВСЕ строки, а не только нетронутые.
Отличить «выключил сознательно» от «не заходил в приватность» в БД нечем —
отметки о взаимодействии нет. Цифры по проду печатаются перед записью,
смотрите их в выводе: если окажется, что осмысленных витрин много, лучше
остановиться и разобрать поимённо.

ВАЖНО: у компании за тумблерами прячется в том числе адрес и состав
команды — это чувствительнее, чем витрина рекрутера. Поэтому скрипт
показывает, у скольких компаний тумблеры уже были включены вручную: если
таких заметная доля, значит люди этим экраном пользуются осознанно.

Запуск: python3 migrate_company_privacy_default.py [--dry-run]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "gambling_community.sqlite3"
FIELDS = (
    "show_name", "show_company", "show_vertical", "show_profession",
    "show_cv", "show_contacts", "show_offers",
)


def main(dry_run: bool) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) AS n FROM guro_company_profiles").fetchone()["n"]
    active = conn.execute(
        "SELECT COUNT(*) AS n FROM guro_company_profiles WHERE subscription_status = 'active'"
    ).fetchone()["n"]
    touched = conn.execute(
        "SELECT COUNT(*) AS n FROM guro_company_profiles WHERE "
        + " OR ".join(f"{f}=1" for f in FIELDS)
    ).fetchone()["n"]
    print(f"guro_company_profiles: {total} строк, из них с активной подпиской {active}")
    print(f"хотя бы один тумблер уже включён вручную: {touched}")

    for field in FIELDS:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM guro_company_profiles WHERE {field}=0 OR {field} IS NULL"
        ).fetchone()
        print(f"  {field}: будет включено у {row['n']} из {total}")

    if dry_run:
        print("\nСУХОЙ ПРОГОН, ничего не записано.")
        return

    for field in FIELDS:
        conn.execute(
            f"UPDATE guro_company_profiles SET {field}=1 WHERE {field}=0 OR {field} IS NULL"
        )
    conn.commit()
    print("\nГОТОВО")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
