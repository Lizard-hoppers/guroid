// Обёртка над Telegram WebApp SDK (грузится тегом <script> в index.html,
// глобально как window.Telegram.WebApp — так же, как раньше, никакого
// отдельного npm-пакета для этого нет и не было).

const tg = typeof window !== "undefined" ? window.Telegram?.WebApp : undefined;

export function initTelegram() {
  if (!tg) return;
  tg.ready();
  tg.expand();
  if (tg.setHeaderColor) tg.setHeaderColor("#071510");
  if (tg.setBackgroundColor) tg.setBackgroundColor("#071510");
}

export function getInitData() {
  return tg?.initData || "";
}

export function haptic(kind = "light") {
  const h = tg?.HapticFeedback;
  if (!h) return;
  if (kind === "success" || kind === "error" || kind === "warning") {
    h.notificationOccurred(kind);
  } else if (kind === "select") {
    h.selectionChanged();
  } else {
    h.impactOccurred(kind); // light | medium | heavy | rigid | soft
  }
}

export function openTelegramLink(url) {
  if (tg?.openTelegramLink) tg.openTelegramLink(url);
  else window.open(url, "_blank");
}

export function openInvoice(url, callback) {
  if (tg?.openInvoice) tg.openInvoice(url, callback);
  else window.open(url, "_blank");
}

// initDataUnsafe.user.photo_url — реальное фото профиля Telegram, если
// клиент его отдаёт (не всегда — тогда фолбэк на буквенный аватар в UI).
export function getAvatarUrl() {
  return tg?.initDataUnsafe?.user?.photo_url || null;
}

// "Добавить на рабочий стол" (Bot API 8.0+, 11.08.2026 — владелец пробовал
// и не нашёл такой опции). Метод есть не у всех клиентов/версий — прячем
// кнопку, если SDK его не отдаёт, вместо вызова и тихого no-op/ошибки.
export function canAddToHomeScreen() {
  return typeof tg?.addToHomeScreen === "function";
}

export function addToHomeScreen() {
  if (canAddToHomeScreen()) tg.addToHomeScreen();
}
