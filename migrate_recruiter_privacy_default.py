"""Одноразовая миграция (06.09.2026): включает тумблеры видимости кабинета
рекрутера у уже существующих строк — «рекрутер каб.pdf», стр. 2,
«Включить тумблеры по умолчанию (чтобы зелёными были как на скрине)».

Колонки уже есть в проде со старым default=0, а ALTER TABLE ADD COLUMN не
переписывает существующую колонку — поэтому нового DEFAULT в
guro_storage.py._init хватает только для свежих БД. Здесь переводим
хранимые значения.

ОСОЗНАННОЕ ДОПУЩЕНИЕ: переводим ВСЕ строки, а не только нетронутые.
Отличить «человек сознательно выключил» от «так и не заходил в
приватность» в БД нечем — отдельной отметки о взаимодействии нет.

Проверено на проде перед запуском (06.09.2026): 50 строк, из них подписка
активна у 3, хоть одно поле витрины заполнено у 2, хоть один тумблер
включён у 1. Строка заводится при первом открытии вкладки «Рекрутер», ещё
до оплаты, — поэтому остальные 47 это пустые заготовки, у которых витрины
нет вовсе. Сознательно выключенных тумблеров среди них нет, а обратный тап
стоит одно нажатие.

Запуск: python3 migrate_recruiter_privacy_default.py [--dry-run]
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

    total = conn.execute("SELECT COUNT(*) AS n FROM guro_recruiter_profiles").fetchone()["n"]
    print(f"guro_recruiter_profiles: {total} строк")

    for field in FIELDS:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM guro_recruiter_profiles WHERE {field}=0 OR {field} IS NULL"
        ).fetchone()
        print(f"  {field}: будет включено у {row['n']} из {total}")

    if dry_run:
        print("\nСУХОЙ ПРОГОН, ничего не записано.")
        return

    for field in FIELDS:
        conn.execute(
            f"UPDATE guro_recruiter_profiles SET {field}=1 WHERE {field}=0 OR {field} IS NULL"
        )
    conn.commit()
    print("\nГОТОВО")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
