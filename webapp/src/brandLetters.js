// Общий список букв "GURO ID" с уникальными id — используется И в
// SlotIntro.jsx (буквы в барабане), И в App.jsx (буквы в шапке). Один и
// тот же id даёт framer-motion `layoutId`, по которому ОДИН И ТОТ ЖЕ
// элемент едет из барабана в шапку, меняя по пути позицию и размер, —
// а не появляется новый текстовый блок.
export const BRAND_LETTERS = [
  { id: "g", char: "G" },
  { id: "u", char: "U" },
  { id: "r", char: "R" },
  { id: "o", char: "O" },
  { id: "i", char: "I" },
  { id: "d", char: "D" },
];

export const BRAND_WORD_1 = BRAND_LETTERS.slice(0, 4);
export const BRAND_WORD_2 = BRAND_LETTERS.slice(4, 6);

// Фирменный градиент надписи идёт СКВОЗЬ всё слово по горизонтали
// (замер по макету: вдоль штриха буквы цвет постоянен, поперёк слова —
// уходит от лайма к циану). Буквы живут отдельными элементами ради
// layoutId, поэтому общая растяжка нарезана по буквам: каждой достаётся
// свой отрезок, и стык в стык они складываются в один градиент.
// Слотов семь — шесть букв и пробел между словами, который тоже занимает
// ширину: G U R O _ I D.
const GRADIENT_FROM = [0xaa, 0xf6, 0x4a]; // --gold
const GRADIENT_TO = [0x0f, 0xd5, 0xf0]; // --recruiter-cyan
const SLOTS = 7;
const LETTER_SLOT = [0, 1, 2, 3, 5, 6];

function stopAt(t) {
  const ch = GRADIENT_FROM.map((from, i) => Math.round(from + (GRADIENT_TO[i] - from) * t));
  return `#${ch.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

export const BRAND_GRADIENT = BRAND_LETTERS.map((l, i) => ({
  ...l,
  from: stopAt(LETTER_SLOT[i] / SLOTS),
  to: stopAt((LETTER_SLOT[i] + 1) / SLOTS),
}));

export const BRAND_GRADIENT_1 = BRAND_GRADIENT.slice(0, 4);
export const BRAND_GRADIENT_2 = BRAND_GRADIENT.slice(4, 6);
