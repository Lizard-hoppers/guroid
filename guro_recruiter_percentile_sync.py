"""Периодический скрипт (systemd timer, раз в сутки): пересчитывает и
кеширует процентиль кабинета "Рекрутер" (ТЗ "Гуро рекрутер каб", раздел
2.5) — R_найм = 100×(1−e^(−W_найм/40)) по КАЖДОМУ рекрутеру с хотя бы
одним подтверждённым наймом, сравнение внутри одной вертикали
(guro_recruiter_profiles.vertical, точное совпадение строки).

Явно НЕ считается в реальном времени по запросу (ТЗ: "пересчёт раз в
сутки, кешировать результат") — /api/me?workspace=recruiter только читает
кэш (см. GuroStorage.get_recruiter_percentile), этот скрипт — единственное
место, где кэш обновляется. Отдельный процесс — тот же принцип изоляции,
что у guro_tags_sync.py/guro_partnership_sync.py."""
from __future__ import annotations

import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import guro_constants as GC
import guro_logic as GL
from config import Settings
from guro_storage import GuroStorage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("guro_recruiter_percentile_sync")


def main() -> None:
    settings = Settings.from_env()
    storage = GuroStorage(settings.database_path)

    pairs = storage.list_recruiter_verticals_with_hires()  # [(user_id, vertical), ...]
    by_vertical: dict[str, list[int]] = defaultdict(list)
    for user_id, vertical in pairs:
        by_vertical[vertical].append(user_id)

    logger.info("вертикалей с рекрутерами-наймами: %s", len(by_vertical))
    updated = 0
    for vertical, user_ids in by_vertical.items():
        total = len(user_ids)
        if total < GC.RECRUITER_PERCENTILE_MIN_SAMPLE:
            # Недостаточно рекрутеров в вертикали — блок не показывается
            # вообще (ТЗ 2.5). Явно чистим кэш, а не оставляем старый.
            for uid in user_ids:
                storage.set_recruiter_percentile(uid, None)
                updated += 1
            logger.info("вертикаль %s: %s рекрутеров < минимума %s, tier=None всем",
                        vertical, total, GC.RECRUITER_PERCENTILE_MIN_SAMPLE)
            continue

        w_by_user = {uid: storage.hire_w(uid) for uid in user_ids}
        sorted_w = sorted(w_by_user.values())
        for uid, w in w_by_user.items():
            r = GL.reputation_from_w(w)
            rank_below = sum(1 for other_w in sorted_w if GL.reputation_from_w(other_w) < r)
            pct = GL.percentile_of(rank_below, total)
            tier = GL.percentile_tier(pct)
            storage.set_recruiter_percentile(uid, tier)
            updated += 1
        logger.info("вертикаль %s: %s рекрутеров, кэш обновлён", vertical, total)

    logger.info("готово, обновлено записей: %s", updated)


if __name__ == "__main__":
    main()
