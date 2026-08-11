import { useEffect, useRef, useState } from "react";
import { motion, useAnimation, useMotionValue, useSpring, useTransform, useVelocity } from "framer-motion";
import { useLang } from "../i18n.jsx";

function IconUser(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="tab-icon" {...props}>
      <circle cx="12" cy="8" r="3.6" />
      <path d="M4.5 20c1.2-4 4.2-6 7.5-6s6.3 2 7.5 6" strokeLinecap="round" />
    </svg>
  );
}

function IconSearch(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="tab-icon" {...props}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M20 20l-4.3-4.3" strokeLinecap="round" />
    </svg>
  );
}

function IconHandshake(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="tab-icon" {...props}>
      <path d="M3 12l4-4 4 3 3-3 3 3h4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M9 11l3 3.5L16 11" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconStar(props) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="tab-icon" {...props}>
      <path d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.6 6.1 20.6l1.3-6.6L2.5 9.4l6.6-.8L12 2.5z" />
    </svg>
  );
}

function IconBriefcase(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="tab-icon" {...props}>
      <rect x="3.5" y="7.5" width="17" height="12" rx="2" />
      <path d="M8.5 7.5V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3.5 12.5h17" strokeLinecap="round" />
    </svg>
  );
}

const TABS = [
  { key: "profile", labelKey: "tab.profile", Icon: IconUser },
  { key: "search", labelKey: "tab.search", Icon: IconSearch },
  { key: "vacancies", labelKey: "tab.vacancies", Icon: IconBriefcase },
  { key: "confirm", labelKey: "tab.confirm", Icon: IconHandshake },
  { key: "subscribe", labelKey: "tab.subscribe", Icon: IconStar },
];

// Пружина ближе к iOS-стилю "liquid glass": высокое демпфирование
// относительно жёсткости (коэфф. затухания ~0.85) — капля мягко доезжает
// до цели с едва заметным одним лёгким проскоком, БЕЗ дребезга из
// нескольких колебаний туда-сюда (тот старый вариант с damping:11 выглядел
// нервно, а не плавно).
const WOBBLE = { type: "spring", stiffness: 280, damping: 28, mass: 1 };

export function TabBar({ active, onChange }) {
  const { t } = useLang();
  const barRef = useRef(null);
  const [tabWidth, setTabWidth] = useState(0);
  const x = useMotionValue(0);
  const controls = useAnimation();
  const isDragging = useRef(false);
  const activeIndex = Math.max(0, TABS.findIndex((t) => t.key === active));

  // Живая, "желейная" деформация — капля растягивается/скашивается по
  // скорости своего движения (и во время реального drag, и во время
  // авто-пружины при обычном тапе на таб) и сама пружинит обратно в
  // нормальную форму, когда останавливается. useVelocity читает скорость
  // изменения x, useSpring сглаживает её, useTransform превращает в
  // scaleX/skewX — классический приём для "сочных" перетаскиваемых элементов.
  const xVelocity = useVelocity(x);
  // Ещё мягче сглаживание, чем в прошлой версии (та тоже дёргалась) —
  // низкая stiffness/высокий damping здесь работают как фильтр низких
  // частот на скорость указателя, срезая мелкий "шум" в сырых координатах.
  // Плюс шире диапазон и меньше максимум деформации — растяжение едва
  // уловимо-живое, а не хлёсткое.
  const smoothVelocity = useSpring(xVelocity, { damping: 70, stiffness: 100 });
  const scaleX = useTransform(smoothVelocity, [-3000, 0, 3000], [1.1, 1, 1.1], { clamp: true });
  const skewX = useTransform(smoothVelocity, [-3000, 0, 3000], [-3, 0, 3], { clamp: true });

  useEffect(() => {
    function measure() {
      if (barRef.current) setTabWidth(barRef.current.offsetWidth / TABS.length);
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  useEffect(() => {
    // Пока капля реально в руках (isDragging) — её позицией управляет
    // сам жест (x привязан к указателю), а не эта пружина; если дать
    // здесь сработать controls.start, они будут воевать за x одновременно,
    // и капля будет дёргаться обратно, пока её всё ещё тащат.
    if (!tabWidth || isDragging.current) return;
    controls.start({ x: activeIndex * tabWidth, transition: WOBBLE });
  }, [activeIndex, tabWidth, controls]);

  function indexFromX() {
    return Math.max(0, Math.min(TABS.length - 1, Math.round(x.get() / tabWidth)));
  }

  function handleDragStart() {
    isDragging.current = true;
  }

  // Живое переключение прямо во время перетаскивания — раздел под каплей
  // должен проявляться сразу, как только она оказалась над ним, а не
  // только после того, как палец отпустят.
  function handleDrag() {
    if (!tabWidth) return;
    const index = indexFromX();
    if (TABS[index].key !== active) onChange(TABS[index].key);
  }

  function snapToNearest() {
    isDragging.current = false;
    if (!tabWidth) return;
    const index = indexFromX();
    controls.start({ x: index * tabWidth, transition: WOBBLE });
    if (TABS[index].key !== active) onChange(TABS[index].key);
  }

  return (
    <nav className="tabbar" ref={barRef}>
      {tabWidth > 0 && (
        <motion.div
          className="tab-blob"
          style={{ width: tabWidth, x, scaleX, skewX }}
          animate={controls}
          drag="x"
          dragConstraints={barRef}
          dragElastic={0.15}
          dragMomentum={false}
          onDragStart={handleDragStart}
          onDrag={handleDrag}
          onDragEnd={snapToNearest}
          whileTap={{ scaleY: 0.93 }}
        />
      )}
      {TABS.map(({ key, labelKey, Icon }) => {
        const isActive = active === key;
        return (
          <button
            key={key}
            type="button"
            className={`tab${isActive ? " is-active" : ""}`}
            onClick={() => onChange(key)}
          >
            <Icon />
            <span className="tab-label">{t(labelKey)}</span>
          </button>
        );
      })}
    </nav>
  );
}
