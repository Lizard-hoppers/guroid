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

// Русская плюрализация (15.08.2026, фидбек владельца — "3 дней" звучит
// коряво, должно быть "3 дня"): 1/21/31.. -> forms[0], 2-4/22-24.. ->
// forms[1], остальное (0, 5-20, 25-30..) -> forms[2]. Стандартное правило
// (11-14 всегда "many", несмотря на то что оканчиваются на 1-4).
export function pluralRu(n, forms) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
  return forms[2];
}

// Люди чаще всего пишут сайт без схемы ("example.com") — без неё <a href>
// трактует ссылку как ОТНОСИТЕЛЬНУЮ (уводит внутри самого Mini App вместо
// открытия внешнего сайта), 16.08.2026, фидбек владельца ("сайт должен
// быть кликабельным в карточке").
export function ensureHttpUrl(url) {
  if (!url) return url;
  return /^https?:\/\//i.test(url) ? url : `https://${url}`;
}
