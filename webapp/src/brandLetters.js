// Общий список букв "GURO ID" с уникальными id — используется И в
// SlotIntro.jsx (буквы в барабане), И в App.jsx (буквы в шапке). Один и тот
// же id у буквы в обоих местах даёт framer-motion `layoutId`, по которому
// ОДИН И ТОТ ЖЕ элемент (не новый текстовый блок!) едет из барабана в шапку,
// меняя по пути позицию и размер (shared layout transition).
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
