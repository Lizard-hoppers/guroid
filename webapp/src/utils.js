const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

// Формат в БД (guro_logic.DATE_FMT): "%Y-%m-%d %H:%M:%S" (UTC, без зоны).
export function formatDate(dbDateString) {
  if (!dbDateString) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dbDateString);
  if (!m) return dbDateString;
  const [, y, mo, d] = m;
  return `${parseInt(d, 10)} ${MONTHS[parseInt(mo, 10) - 1]} ${y}`;
}

export function initialOf(name, username) {
  const source = (name || username || "?").trim();
  return source.charAt(0).toUpperCase() || "?";
}
