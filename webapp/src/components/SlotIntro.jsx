import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BRAND_WORD_1, BRAND_WORD_2 } from "../brandLetters.js";

const FILLER = ["X", "7", "J", "Q", "$", "Z"];
const CELL_HEIGHT = 52; // совпадает с .reel-cell{height:52px} в styles.css
// Целевая буква — ПОСЛЕДНЯЯ ячейка в ленте (после всех filler), поэтому
// конечное смещение должно поднять ленту ровно на неё, а не вернуть к нулю.
const FINAL_Y = -FILLER.length * CELL_HEIGHT;

const SETTLE_AT_MS = 1450; // когда долетел последний (самый поздний) барабан
const BARREL_FADE_MS = 280; // рамки барабана растворяются, буквы остаются на месте

function Reel({ letter, delay }) {
  return (
    <div className="reel-window">
      <motion.div
        className="reel-strip"
        initial={{ y: 0 }}
        animate={{ y: FINAL_Y }}
        transition={{ delay, duration: 0.85, ease: [0.15, 0.9, 0.25, 1] }}
      >
        {FILLER.map((c, idx) => (
          <div className="reel-cell" key={idx}>
            {c}
          </div>
        ))}
        <div className="reel-cell">{letter}</div>
      </motion.div>
    </div>
  );
}

// Декоративная заставка при старте Mini App — барабаны складывают "GURO ID"
// (тема казино-комьюнити). КЛЮЧЕВОЕ: когда рамки барабана растворяются,
// НЕ появляется новый текстовый блок — остаются ТЕ ЖЕ САМЫЕ 6 букв
// (каждая свой layoutId, см. brandLetters.js), просто без рамки-окошка
// вокруг. Они летят наверх в шапку (App.jsx, там те же layoutId у каждой
// буквы) — framer-motion сам анимирует КАЖДУЮ букву индивидуально из её
// позиции в барабане в её точную позицию внутри слова в шапке, с
// уменьшением размера по пути (shared layout transition на 6 элементах,
// а не на одной строке текста).
export function SlotIntro({ onDone }) {
  const [settled, setSettled] = useState(false);

  useEffect(() => {
    const t1 = setTimeout(() => setSettled(true), SETTLE_AT_MS);
    const t2 = setTimeout(onDone, SETTLE_AT_MS + BARREL_FADE_MS);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [onDone]);

  return (
    <motion.div className="slot-overlay" exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
      <div className="slot-stage">
        <AnimatePresence>
          {!settled ? (
            <motion.div key="reels" className="slot-row" exit={{ opacity: 0 }} transition={{ duration: 0.24 }}>
              {BRAND_WORD_1.map((l, i) => (
                <Reel key={l.id} letter={l.char} delay={i * 0.12} />
              ))}
              <div className="slot-gap" />
              {BRAND_WORD_2.map((l, i) => (
                <Reel key={l.id} letter={l.char} delay={(BRAND_WORD_1.length + i) * 0.12} />
              ))}
            </motion.div>
          ) : (
            <div key="letters" className="slot-row slot-row-bare">
              {BRAND_WORD_1.map((l) => (
                <motion.div key={l.id} layoutId={`brand-${l.id}`} className="brand-hero-letter">
                  {l.char}
                </motion.div>
              ))}
              <div className="slot-gap" />
              {BRAND_WORD_2.map((l) => (
                <motion.div key={l.id} layoutId={`brand-${l.id}`} className="brand-hero-letter">
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
