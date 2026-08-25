"""Периодический скрипт (systemd timer): доводит до конца две отложенные
механики формулы рейтинга v2 (ТЗ "Сделка, формула рейтинга, анти-абьюз",
25.08.2026), которые не могут сработать мгновенно в момент HTTP-запроса:

1. Раскрытие оценок Шага 2 по ТАЙМАУТУ (6.1) — если только ОДНА сторона
   поставила оценку и обе стороны не успели за RATING_REVEAL_TIMEOUT_DAYS,
   раскрываем то, что есть (мгновенное раскрытие "обе сразу" уже
   происходит синхронно в guro_storage.submit_rating).
2. Досинк "Найма" (6, п.3) — партнёрство подтверждено, но кандидат ещё не
   переключил work_status на "работаю"; очки отложены (hire_status_pending).
   Проверяем заново на каждый тик, применяем, как только статус совпал.

Отдельный процесс от бота — тот же принцип изоляции, что у
guro_tags_sync.py/news_poster.py."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Settings
from guro_storage import GuroStorage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("guro_partnership_sync")


def main() -> None:
    settings = Settings.from_env()
    storage = GuroStorage(settings.database_path)

    awaiting = storage.list_partnerships_awaiting_reveal()
    logger.info("раскрытие оценок по таймауту: %s партнёрств просрочено", len(awaiting))
    for p in awaiting:
        storage.reveal_rating_by_timeout(p["id"])

    hire_pending = storage.list_hire_pending_partnerships()
    logger.info("найм в ожидании статуса кандидата: %s партнёрств", len(hire_pending))
    synced = 0
    for p in hire_pending:
        if storage.sync_hire_status(p["id"]):
            synced += 1
    logger.info("статус кандидата синхронизирован и очки применены: %s", synced)


if __name__ == "__main__":
    main()
