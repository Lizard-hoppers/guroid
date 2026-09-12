import { useEffect, useRef, useState } from "react";
import {
  motion, useAnimation, useMotionTemplate, useMotionValue, useSpring, useTransform, useVelocity,
} from "framer-motion";
import { useLang } from "../i18n.jsx";

// 12.09.2026 — геометрия сверена с эталонным исполняемым компонентом
// GuroTabs.dc.html: viewBox 20 (не 24), обводка 1.5 (не 1.8/1.9 —
// значение для этого конкретного компонента переопределено отдельно от
// общего правила раздела 6). Пропорции круга/дуги — оттуда же, не "на глаз".
function IconUser(props) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="tab-icon" {...props}>
      <circle cx="10" cy="7" r="3.1" />
      <path d="M4.2 16.6c1.4-2.9 10.2-2.9 11.6 0" strokeLinecap="round" />
    </svg>
  );
}

function IconSearch(props) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="tab-icon" {...props}>
      <circle cx="9" cy="9" r="5" />
      <path d="M12.8 12.8 17 17" strokeLinecap="round" />
    </svg>
  );
}

// Галочка — как в макете таб-бара (полный набор, стр. 3) и по правилу
// раздела 6 «один смысл — одна иконка»: галочка у нас уже означает
// «подтверждено», и вкладка про подтверждение рисуется тем же знаком.
// Прежнее рукопожатие снято — после замены его никто не использовал.
function IconConfirm(props) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="tab-icon" {...props}>
      <path d="M3.5 10.5 8 15l8.5-9.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// 12.09.2026 — эталон рисует звезду ЛИНИЕЙ (stroke, без заливки), не
// закрашенной фигурой. Прежняя fill="currentColor" версия нарушала
// правило раздела 6 "только линейные SVG, без заливки" — единственная
// заливная иконка во всём приложении, просто никогда не сверялась с
// правилом, потому что живёт отдельно от общего набора в Icons.jsx.
function IconStar(props) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="tab-icon" {...props}>
      <path d="M10 2.6l2.29 4.9 5.11.62-3.75 3.6.98 5.28L10 14.44l-4.63 2.56.98-5.28L2.6 8.12l5.11-.62z" />
    </svg>
  );
}

// Без средней горизонтальной черты-разделителя — у эталона её нет,
// раньше была добавлена от себя.
function IconBriefcase(props) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="tab-icon" {...props}>
      <rect x="2.5" y="6" width="15" height="10.5" rx="2.2" />
      <path d="M7.5 6V4.5h5V6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const TABS = [
  { key: "profile", labelKey: "tab.profile", Icon: IconUser },
  { key: "search", labelKey: "tab.search", Icon: IconSearch },
  { key: "vacancies", labelKey: "tab.vacancies", Icon: IconBriefcase },
  { key: "confirm", labelKey: "tab.confirm", Icon: IconConfirm },
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
  // Спекулярный блик, откликающийся на движение (Apple HIG, Materials:
  // «specular highlights respond to device motion»). Блик отстаёт от
  // движения — смещается ПРОТИВ хода капли, как отражение на стекле,
  // и разгорается тем сильнее, чем быстрее она едет.
  const specX = useTransform(smoothVelocity, [-3000, 0, 3000], [14, 0, -14], { clamp: true });
  const specOpacity = useTransform(
    smoothVelocity, [-3000, -600, 0, 600, 3000], [0.36, 0.22, 0.16, 0.22, 0.36], { clamp: true },
  );
  // Готовим строку на ВЕРХНЕМ уровне компонента: сама капля отрисовывается
  // условно (tabWidth > 0), и вызов хука внутри той ветки сделал бы его
  // условным — React такого не допускает.
  const specXCss = useMotionTemplate`${specX}px`;

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
          style={{
            width: tabWidth,
            x,
            scaleX,
            skewX,
            "--spec-x": specXCss,
            "--spec-opacity": specOpacity,
          }}
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
