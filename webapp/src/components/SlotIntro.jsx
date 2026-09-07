import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BRAND_WORD_1, BRAND_WORD_2 } from "../brandLetters.js";

// Заставка при старте Mini App — слот-барабаны складывают "GURO ID"
// (05.09.2026, файл владельца zastavka2.gif).
//
// Гифка НЕ вшивается: она весит 4.3 МБ при бандле приложения в 528 КБ,
// то есть экран загрузки сам стал бы тем, что грузится. Анимация здесь
// чисто механическая (ленты букв + сдвиг), поэтому воспроизведена кодом —
// ноль килобайт, резко на любой плотности экрана и точные цвета токенов.
// Все величины сняты замером с кадров гифки (масштаб 390/1080):
//     шаг ячейки          60pt
//     высота окна        130pt
//     кегль буквы   cap 43pt -> ~58px
//     разделитель          1px, белый
//     ширина строки      350pt
//     один проход       2.83 c, барабаны докручиваются к ~2.6 c
// Проход ужат до ~2.4 c: дальше буквы переезжают в шапку (см. layoutId
// ниже) — этого в гифке нет, но такой переход в приложении уже был до
// 28.08.2026 и он оправдывает, почему заставка вообще уходит.
//
// Фон взят --bg-deep, а не чёрный как в гифке: чёрный прямоугольник
// заметно спорил бы с фоном приложения и с градиентной обводкой экрана.

const FILLER = ["X", "J", "M", "W", "F", "Q", "Z", "Y"];
const CELL_H = 90; // .reel-cell height
const WINDOW_H = 130; // .reel-window height
// Целевая буква — последняя ячейка ленты, её нужно вывести в ЦЕНТР окна,
// а не просто поднять к его верхней кромке.
const FINAL_Y = -(FILLER.length * CELL_H) + (WINDOW_H - CELL_H) / 2;

const SPIN_MS = 900; // прокрутка одного барабана
const STAGGER_MS = 140; // барабаны садятся слева направо
const SETTLE_LAST_MS = SPIN_MS + STAGGER_MS * 5; // 1600
const BARE_AT_MS = SETTLE_LAST_MS + 350; // рамки гаснут, буквы остаются
const DONE_MS = BARE_AT_MS + 450; // 2400

function Reel({ letter, accent, index }) {
  return (
    <div className="reel-window">
      <motion.div
        className="reel-strip"
        initial={{ y: 0, filter: "blur(2.5px)" }}
        animate={{ y: FINAL_Y, filter: "blur(0px)" }}
        transition={{
          delay: (index * STAGGER_MS) / 1000,
          duration: SPIN_MS / 1000,
          ease: [0.12, 0.8, 0.2, 1],
        }}
      >
        {FILLER.map((c, i) => (
          <div className="reel-cell" key={i}>
            {c}
          </div>
        ))}
        <div className={`reel-cell${accent ? " reel-cell--accent" : ""}`}>{letter}</div>
      </motion.div>
    </div>
  );
}

export function SlotIntro({ onDone }) {
  const [bare, setBare] = useState(false);

  useEffect(() => {
    const t1 = setTimeout(() => setBare(true), BARE_AT_MS);
    const t2 = setTimeout(onDone, DONE_MS);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [onDone]);

  return (
    <motion.div className="slot-overlay" exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
      {/* .slot-stage обязателен: в момент подмены оба состояния живут в
          DOM одновременно, и без наложения друг на друга буквы уезжают
          вбок — см. комментарий к .slot-stage в styles.css. */}
      <div className="slot-stage">
        <AnimatePresence>
          {!bare ? (
            <motion.div key="reels" className="slot-row" exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
              {BRAND_WORD_1.map((l, i) => (
                <Reel key={l.id} letter={l.char} index={i} />
              ))}
              {BRAND_WORD_2.map((l, i) => (
                <Reel key={l.id} letter={l.char} index={BRAND_WORD_1.length + i} accent />
              ))}
            </motion.div>
          ) : (
            // Рамки-разделители исчезли, а буквы остались ТЕ ЖЕ САМЫЕ: у
            // каждой свой layoutId, такой же стоит у буквы в шапке
            // (App.jsx). framer-motion сам перевозит каждую букву из её
            // ячейки в её место в заголовке, уменьшая по дороге, — это не
            // новый текстовый блок, а тот же элемент.
            <div key="letters" className="slot-row slot-row--bare">
              {BRAND_WORD_1.map((l) => (
                <motion.div key={l.id} layoutId={`brand-${l.id}`} className="slot-letter">
                  {l.char}
                </motion.div>
              ))}
              {BRAND_WORD_2.map((l) => (
                <motion.div
                  key={l.id}
                  layoutId={`brand-${l.id}`}
                  className="slot-letter slot-letter--accent"
                >
                  {l.char}
                </motion.div>
              ))}
            </div>
            )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
