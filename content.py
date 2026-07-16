"""Эффективный контент: CMS-override из БД, иначе дефолт из constants.

Используется во всех клавиатурах и текстах флоу, чтобы правки из админ-раздела
«Контент» применялись на лету, без перезапуска бота.
"""
from __future__ import annotations

import constants as C


class Content:
    def __init__(self, storage):
        self.storage = storage

    def btn(self, key: str) -> str:
        override = self.storage.get_button_override(key)
        if override:
            return override
        return C.BUTTON_DEFAULTS.get(key, key)

    def txt(self, key: str) -> str:
        override = self.storage.get_text_override(key)
        if override:
            return override
        return C.TEXT_DEFAULTS.get(key, "")

    def media(self, key: str):
        """(file_id, media_type) если на экран задано медиа, иначе None."""
        return self.storage.get_media(key)

    def view(self, lang: str):
        """Языковое представление контента: 'en' → ключи с суффиксом _en."""
        if lang == "en":
            return LangContent(self)
        return self


class LangContent:
    """EN-обёртка: override/дефолт ключа «key_en», иначе базовый «key».

    Данные (вертикали/грейды/должности) EN-двойников не имеют и падают в базу.
    """

    def __init__(self, base: Content):
        self._base = base
        self.storage = base.storage

    def btn(self, key: str) -> str:
        override = self.storage.get_button_override(f"{key}_en")
        if override:
            return override
        default = C.BUTTON_DEFAULTS.get(f"{key}_en")
        if default:
            return default
        return self._base.btn(key)

    def txt(self, key: str) -> str:
        override = self.storage.get_text_override(f"{key}_en")
        if override:
            return override
        default = C.TEXT_DEFAULTS.get(f"{key}_en")
        if default:
            return default
        return self._base.txt(key)

    def media(self, key: str):
        return self.storage.get_media(f"{key}_en") or self._base.media(key)
