// Обёртка над Telegram WebApp SDK (грузится тегом <script> в index.html,
// глобально как window.Telegram.WebApp — так же, как раньше, никакого
// отдельного npm-пакета для этого нет и не было).

const tg = typeof window !== "undefined" ? window.Telegram?.WebApp : undefined;

export function initTelegram() {
  if (!tg) return;
  tg.ready();
  tg.expand();
  if (tg.setHeaderColor) tg.setHeaderColor("#0a181a");
  if (tg.setBackgroundColor) tg.setBackgroundColor("#0a181a");
  applySafeAreaInsets();
  tg.onEvent?.("safeAreaChanged", applySafeAreaInsets);
  tg.onEvent?.("contentSafeAreaChanged", applySafeAreaInsets);
  watchKeyboard();
}

// Открыта ли экранная клавиатура. Отдельного события про неё нет, а
// определить надо: .tabbar — position: fixed, то есть привязан к
// LAYOUT-вьюпорту, и без этого он висит поверх клавиатуры.
//
// Одного признака не хватает, потому что платформы ведут себя по-разному:
//   - где-то клавиатура НАКРЫВАЕТ страницу — тогда visualViewport
//     становится короче окна;
//   - где-то Telegram УЖИМАЕТ САМ ВЕБВЬЮ — тогда innerHeight падает
//     вместе с visualViewport, разница нулевая, и первый признак молчит;
//     на этот случай у Telegram есть своя пара viewportHeight /
//     viewportStableHeight (stable — высота БЕЗ клавиатуры);
//   - плюс самый прямой признак: фокус в текстовом поле, в вебвью
//     клавиатуру больше нечем вызвать.
// Берём ИЛИ по всем трём. Порог 120px — чтобы не ловить мелочь вроде
// панели автоподсказок.
//
// Класс вешаем на <html>, а не держим в React-состоянии: состояние чисто
// визуальное, тащить его через дерево компонентов незачем.
const KEYBOARD_MIN_PX = 120;

function isTextField(el) {
  if (!el) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag !== "INPUT") return false;
  return !["checkbox", "radio", "button", "submit", "reset", "file", "range", "color"].includes(el.type);
}

function watchKeyboard() {
  if (typeof window === "undefined" || typeof document === "undefined") return;
  const root = document.documentElement;
  let focusInField = false;

  function viewportShrunk() {
    const vv = window.visualViewport;
    if (vv && window.innerHeight - vv.height > KEYBOARD_MIN_PX) return true;
    const h = tg?.viewportHeight;
    const stable = tg?.viewportStableHeight;
    if (typeof h === "number" && typeof stable === "number" && stable - h > KEYBOARD_MIN_PX) {
      return true;
    }
    return false;
  }

  function apply() {
    root.classList.toggle("keyboard-open", focusInField || viewportShrunk());
  }

  const vv = window.visualViewport;
  vv?.addEventListener("resize", apply);
  vv?.addEventListener("scroll", apply);
  tg?.onEvent?.("viewportChanged", apply);

  // На десктопном Telegram фокус в поле клавиатуру не поднимает — там
  // остаются только два признака выше.
  if (window.matchMedia?.("(pointer: coarse)")?.matches ?? true) {
    document.addEventListener("focusin", (e) => {
      focusInField = isTextField(e.target);
      apply();
    });
    document.addEventListener("focusout", () => {
      focusInField = false;
      // При переходе между соседними полями focusout приходит РАНЬШЕ
      // focusin — если применить сразу, таббар мигнёт на один кадр.
      setTimeout(apply, 0);
    });
  }

  apply();
}

// Верхний отступ под нативные элементы Telegram (02.09.2026, фидбек
// владельца — заголовок "GURO ID" наезжал на плашку статус-бара и на
// строку Закрыть/Свернуть/Ещё, которую Telegram рисует ПОВЕРХ Mini App в
// развёрнутом состоянии, см. скриншот). Bot API 8.0+ отдаёт ровно под это
// две пары отступов:
// - safeAreaInset — физический safe area устройства (чёлка/статус-бар);
// - contentSafeAreaInset — ДОПОЛНИТЕЛЬНО отступ под собственные элементы
//   управления Telegram (Закрыть/шеврон/меню) поверх этого;
// складываем оба (официальный паттерн из примеров Telegram для
// fullscreen-подобных Mini Apps) и кладём суммой в CSS-переменную, а не
// держим в React-состоянии — это чисто визуальный отступ шапки, не влияет
// ни на какую бизнес-логику, незачем тащить через рендер-дерево.
function applySafeAreaInsets() {
  if (!tg) return;
  const top = (tg.safeAreaInset?.top || 0) + (tg.contentSafeAreaInset?.top || 0);
  document.documentElement.style.setProperty("--tg-safe-top", `${top}px`);
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

// Имя из initData — предзаполняет поле "Имя" в регистрации прямо в
// приложении (11.09.2026), чтобы не заставлять печатать то, что Telegram
// и так знает. Просто подсказка: поле остаётся редактируемым, у части
// людей это не то имя, каким они хотят называться в GURO ID.
export function getSuggestedName() {
  const u = tg?.initDataUnsafe?.user;
  if (!u) return "";
  return [u.first_name, u.last_name].filter(Boolean).join(" ").trim();
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
