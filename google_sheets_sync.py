"""Best-effort синхронизация анкет в Google Sheets.

Если синк выключен или не настроен spreadsheet_id — все методы тихо no-op.
Источник правды — SQLite; запись в таблицу не должна ломать флоу пользователя.
"""
from __future__ import annotations

import logging
from pathlib import Path

from config import Settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "Дата (UTC)", "User ID", "Username", "Вертикаль", "Грейд",
    "Профессия", "Тип инвестора", "Суммы инвестиций", "Что ищет (инвестор)",
    "Запрос (что актуально)", "Имя", "Страна", "Компания", "LinkedIn/контакт",
]


class SheetSync:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._worksheet = None
        self._header_ready = False

    @property
    def enabled(self) -> bool:
        s = self.settings
        return bool(
            s.google_sheets_enabled
            and s.google_sheets_spreadsheet_id
            and s.google_sheets_credentials_path
        )

    def _get_worksheet(self):
        if self._worksheet is not None:
            return self._worksheet
        if not self.enabled:
            return None
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            creds = Credentials.from_service_account_file(
                str(self.settings.google_sheets_credentials_path), scopes=SCOPES
            )
            client = gspread.authorize(creds)
            sh = client.open_by_key(self.settings.google_sheets_spreadsheet_id)
            name = self.settings.google_sheets_worksheet_name
            try:
                ws = sh.worksheet(name)
            except Exception:
                ws = sh.add_worksheet(title=name, rows=1000, cols=len(HEADERS))
            self._worksheet = ws
            self._ensure_header(ws)
            return ws
        except Exception:  # noqa: BLE001 — best-effort, не валим бота
            logger.exception("Google Sheets: не удалось открыть таблицу")
            return None

    def _ensure_header(self, ws) -> None:
        if self._header_ready:
            return
        try:
            first = ws.row_values(1)
            if first[: len(HEADERS)] != HEADERS:
                ws.update(values=[HEADERS], range_name="A1")
            self._header_ready = True
        except Exception:  # noqa: BLE001
            logger.exception("Google Sheets: не удалось проверить заголовок")

    def append_row(self, row: list[str]) -> bool:
        ws = self._get_worksheet()
        if ws is None:
            return False
        try:
            ws.append_row(row, value_input_option="USER_ENTERED")
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Google Sheets: не удалось дописать строку")
            return False
