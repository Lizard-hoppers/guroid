// Набор линейных иконок (дизайн-система, раздел 6, 07.09.2026).
//
// Система запрещает эмодзи в интерфейсе поимённо: «включая ✅ ❌ ⚠ 🔒 🏆 ⭐».
// Причина видна на любом устройстве: эмодзи рисует система, поэтому они
// разного стиля и веса на iOS, Android и в вебвью, не наследуют цвет текста
// и ломают вертикальный ритм строки.
//
// Правила отсюда же:
//   • только stroke, без заливки, скруглённые концы;
//   • толщина по умолчанию 1.9; исключения — треугольник 1.35 и крестик
//     1.55: при равной толщине они выглядят тяжелее остальных;
//   • размер в тексте, чипе и бейдже 13px (высота заглавной буквы),
//     vertical-align: -2px; в таб-баре 20px;
//   • один смысл — одна иконка: галочка = успешно, треугольник = нюансы,
//     крестик = проблема.
//
// Цвет по умолчанию наследуется от текста (currentColor) — так замок и
// кубок и должны себя вести. Статусным иконкам цвет задаётся явно там, где
// они ставятся, чтобы не плодить варианты компонента.

const BASE = 1.9;

function Svg({ size = 13, width = BASE, children, style, ...rest }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={width}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ verticalAlign: -2, flex: "none", ...style }}
      {...rest}
    >
      {children}
    </svg>
  );
}

// Успешно. Цвет по системе — #AAF64A, на лайме #14520A.
export function IconCheck(props) {
  return (
    <Svg {...props}>
      <path d="M20 6 9 17l-5-5" />
    </Svg>
  );
}

// Нюансы. Тоньше остальных (1.35) — иначе треугольник выглядит жирнее.
export function IconWarning(props) {
  return (
    <Svg width={1.35} {...props}>
      <path d="M12 3.8 21 19.2H3L12 3.8Z" />
      <path d="M12 9.6v4.2" />
      <path d="M12 16.6h.01" />
    </Svg>
  );
}

// Проблема. Чуть тоньше базовой (1.55) по той же причине.
export function IconCross(props) {
  return (
    <Svg width={1.55} {...props}>
      <path d="M18 6 6 18M6 6l12 12" />
    </Svg>
  );
}

export function IconLock(props) {
  return (
    <Svg {...props}>
      <rect x="4.5" y="10.5" width="15" height="10" rx="2.5" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
    </Svg>
  );
}

export function IconUnlock(props) {
  return (
    <Svg {...props}>
      <rect x="4.5" y="10.5" width="15" height="10" rx="2.5" />
      <path d="M8 10.5V7.5a4 4 0 0 1 7.7-1.5" />
    </Svg>
  );
}

export function IconTrophy(props) {
  return (
    <Svg {...props}>
      <path d="M7 4h10v5a5 5 0 0 1-10 0V4Z" />
      <path d="M7 6H4.5v1.5A3.5 3.5 0 0 0 8 11" />
      <path d="M17 6h2.5v1.5A3.5 3.5 0 0 1 16 11" />
      <path d="M12 14v3.5M9 20.5h6" />
    </Svg>
  );
}

export function IconStar(props) {
  return (
    <Svg {...props}>
      <path d="M12 3.6l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.5 9.8l5.9-.9L12 3.6Z" />
    </Svg>
  );
}

export function IconEye(props) {
  return (
    <Svg {...props}>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
    </Svg>
  );
}

export function IconReply(props) {
  return (
    <Svg {...props}>
      <path d="M9 5 3 11l6 6" />
      <path d="M3 11h9a8 8 0 0 1 8 8v1" />
    </Svg>
  );
}

export function IconMail(props) {
  return (
    <Svg {...props}>
      <rect x="3" y="5.5" width="18" height="13" rx="2.5" />
      <path d="m3.8 7 8.2 6 8.2-6" />
    </Svg>
  );
}

export function IconGear(props) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 14a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5v.2a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1h.2a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1Z" />
    </Svg>
  );
}

export function IconArrowRight(props) {
  return (
    <Svg {...props}>
      <path d="M4 12h15" />
      <path d="m13 6 6 6-6 6" />
    </Svg>
  );
}

export function IconPlus(props) {
  return (
    <Svg {...props}>
      <path d="M12 5v14M5 12h14" />
    </Svg>
  );
}

export function IconShare(props) {
  return (
    <Svg {...props}>
      <path d="M12 15V3" />
      <path d="m8 7 4-4 4 4" />
      <path d="M4 14v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5" />
    </Svg>
  );
}

export function IconLink(props) {
  return (
    <Svg {...props}>
      <path d="M10 13.5a4 4 0 0 0 5.7 0l3-3a4 4 0 1 0-5.7-5.7l-1.3 1.3" />
      <path d="M14 10.5a4 4 0 0 0-5.7 0l-3 3a4 4 0 1 0 5.7 5.7l1.3-1.3" />
    </Svg>
  );
}

export function IconPerson(props) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="8" r="3.6" />
      <path d="M4.5 20.5a7.5 7.5 0 0 1 15 0" />
    </Svg>
  );
}

export function IconBriefcase(props) {
  return (
    <Svg {...props}>
      <rect x="3" y="7.5" width="18" height="12" rx="2.5" />
      <path d="M9 7.5V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1.5" />
    </Svg>
  );
}

export function IconBuilding(props) {
  return (
    <Svg {...props}>
      <rect x="4.5" y="3.5" width="15" height="17" rx="2" />
      <path d="M9 8h2M13 8h2M9 12h2M13 12h2M10.5 20.5v-4h3v4" />
    </Svg>
  );
}

// "i" в кружке — раскрывает пояснение по тапу (11.09.2026, карточка
// "активации" кабинета). Точка через нулевой отрезок с round linecap —
// тот же приём, что у точки восклицательного знака в IconWarning.
export function IconInfo(props) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 7.5h.01" />
    </Svg>
  );
}
