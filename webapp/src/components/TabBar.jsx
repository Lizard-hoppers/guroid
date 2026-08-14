import { useEffect, useId, useRef, useState } from "react";
import { motion, useAnimation, useMotionValue, useSpring, useTransform, useVelocity } from "framer-motion";
import { useLang } from "../i18n.jsx";
import { generateLiquidGlassDisplacementMap, supportsGlassRefraction } from "../liquidGlass.js";

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

// SVG-цепочка фильтров для преломления + лёгкой хроматической аберрации
// (см. src/liquidGlass.js — там сама displacement-карта и объяснение
// авторства). displacementScale/aberrationIntensity занижены относительно
// дефолтов апстрима (25/2 -> 16/1) — по просьбе владельца "не сильно",
// эффект должен быть заметен, но не кричащим.
const DISPLACEMENT_SCALE = 16;
const ABERRATION_INTENSITY = 1;

function LiquidGlassFilter({ id, width, height, mapUrl }) {
  if (!mapUrl) return null;
  return (
    <svg style={{ position: "absolute", width, height, overflow: "visible" }} aria-hidden="true">
      <defs>
        <radialGradient id={`${id}-edge-mask`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="black" stopOpacity="0" />
          <stop offset={`${Math.max(30, 80 - ABERRATION_INTENSITY * 2)}%`} stopColor="black" stopOpacity="0" />
          <stop offset="100%" stopColor="white" stopOpacity="1" />
        </radialGradient>
        <filter id={id} x="-35%" y="-35%" width="170%" height="170%" colorInterpolationFilters="sRGB">
          <feImage x="0" y="0" width="100%" height="100%" result="DISPLACEMENT_MAP" href={mapUrl} preserveAspectRatio="xMidYMid slice" />
          <feColorMatrix
            in="DISPLACEMENT_MAP"
            type="matrix"
            values="0.3 0.3 0.3 0 0  0.3 0.3 0.3 0 0  0.3 0.3 0.3 0 0  0 0 0 1 0"
            result="EDGE_INTENSITY"
          />
          <feComponentTransfer in="EDGE_INTENSITY" result="EDGE_MASK">
            <feFuncA type="discrete" tableValues={`0 ${ABERRATION_INTENSITY * 0.05} 1`} />
          </feComponentTransfer>
          <feOffset in="SourceGraphic" dx="0" dy="0" result="CENTER_ORIGINAL" />
          <feDisplacementMap in="SourceGraphic" in2="DISPLACEMENT_MAP" scale={DISPLACEMENT_SCALE} xChannelSelector="R" yChannelSelector="B" result="RED_DISPLACED" />
          <feColorMatrix in="RED_DISPLACED" type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="RED_CHANNEL" />
          <feDisplacementMap in="SourceGraphic" in2="DISPLACEMENT_MAP" scale={DISPLACEMENT_SCALE - ABERRATION_INTENSITY * 0.05} xChannelSelector="R" yChannelSelector="B" result="GREEN_DISPLACED" />
          <feColorMatrix in="GREEN_DISPLACED" type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" result="GREEN_CHANNEL" />
          <feDisplacementMap in="SourceGraphic" in2="DISPLACEMENT_MAP" scale={DISPLACEMENT_SCALE - ABERRATION_INTENSITY * 0.1} xChannelSelector="R" yChannelSelector="B" result="BLUE_DISPLACED" />
          <feColorMatrix in="BLUE_DISPLACED" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" result="BLUE_CHANNEL" />
          <feBlend in="GREEN_CHANNEL" in2="BLUE_CHANNEL" mode="screen" result="GB_COMBINED" />
          <feBlend in="RED_CHANNEL" in2="GB_COMBINED" mode="screen" result="RGB_COMBINED" />
          <feGaussianBlur in="RGB_COMBINED" stdDeviation={Math.max(0.1, 0.5 - ABERRATION_INTENSITY * 0.1)} result="ABERRATED_BLURRED" />
          <feComposite in="ABERRATED_BLURRED" in2="EDGE_MASK" operator="in" result="EDGE_ABERRATION" />
          <feComponentTransfer in="EDGE_MASK" result="INVERTED_MASK">
            <feFuncA type="table" tableValues="1 0" />
          </feComponentTransfer>
          <feComposite in="CENTER_ORIGINAL" in2="INVERTED_MASK" operator="in" result="CENTER_CLEAN" />
          <feComposite in="EDGE_ABERRATION" in2="CENTER_CLEAN" operator="over" />
        </filter>
      </defs>
    </svg>
  );
}

export function TabBar({ active, onChange }) {
  const { t } = useLang();
  const barRef = useRef(null);
  const blobRef = useRef(null);
  const filterId = useId();
  const [tabWidth, setTabWidth] = useState(0);
  const [displacementUrl, setDisplacementUrl] = useState("");
  const x = useMotionValue(0);
  const controls = useAnimation();
  const isDragging = useRef(false);
  const activeIndex = Math.max(0, TABS.findIndex((t) => t.key === active));
  const glassSupported = supportsGlassRefraction();

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
    // ВАЖНО: не offsetWidth(bar)/5 — .tabbar имеет собственный горизонтальный
    // padding (см. styles.css), который offsetWidth включает, а реальные
    // кнопки-табы внутри него — нет. Такое расхождение накапливалось от
    // таба к табу и на последнем табе капля уезжала на ~10px в сторону от
    // центра (баг с "капля съезжает к краю экрана", 14.08.2026). Меряем
    // ширину РЕАЛЬНОЙ кнопки напрямую — не зависит от паддингов/гэпов.
    function measure() {
      const tabEl = barRef.current?.querySelector(".tab");
      if (tabEl) setTabWidth(tabEl.offsetWidth);
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  useEffect(() => {
    // Карта преломления строится ОДИН раз на размер капли (не на кадр/драг —
    // см. liquidGlass.js) и только пересчитывается при реальном ресайзе
    // экрана (тот же tabWidth). blobRef уже примонтирован к этому моменту —
    // капля рендерится в той же ветке JSX, что зависит от tabWidth>0, а
    // этот эффект срабатывает ПОСЛЕ коммита DOM.
    if (!tabWidth || !glassSupported) return;
    const height = blobRef.current?.offsetHeight || 44;
    const url = generateLiquidGlassDisplacementMap(tabWidth, height);
    if (url) setDisplacementUrl(url);
  }, [tabWidth, glassSupported]);

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
      {tabWidth > 0 && glassSupported && displacementUrl && (
        <LiquidGlassFilter id={filterId} width={tabWidth} height={blobRef.current?.offsetHeight || 44} mapUrl={displacementUrl} />
      )}
      {tabWidth > 0 && (
        <motion.div
          ref={blobRef}
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
        >
          {glassSupported && displacementUrl && (
            <span className="tab-blob-warp" style={{ filter: `url(#${filterId})` }} />
          )}
        </motion.div>
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
