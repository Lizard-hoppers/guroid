import { useEffect, useRef, useState } from "react";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { initTelegram } from "./telegram.js";
import { TabBar } from "./components/TabBar.jsx";
import { ProfileScreen } from "./components/ProfileScreen.jsx";
import { SearchScreen } from "./components/SearchScreen.jsx";
import { ConfirmScreen } from "./components/ConfirmScreen.jsx";
import { SubscribeScreen } from "./components/SubscribeScreen.jsx";
import { VacanciesScreen } from "./components/VacanciesScreen.jsx";
import { SlotIntro } from "./components/SlotIntro.jsx";
import { BRAND_WORD_1, BRAND_WORD_2 } from "./brandLetters.js";
import { LangProvider, useLang } from "./i18n.jsx";

// Переключатель RU/EN в правом верхнем углу (12.08.2026, по просьбе
// владельца) — текстовые буквы, не флаги (тот же принцип, что и у
// языковых кнопок бота, см. constants.py: без флага РФ). Каждый
// компонент читает язык через useLang() напрямую (React Context) —
// проп через весь дерево тянуть не нужно.
function LanguageSwitch() {
  const { lang, setLang } = useLang();
  return (
    <div className="lang-switch">
      <button type="button" className={lang === "ru" ? "is-active" : ""} onClick={() => setLang("ru")}>
        RU
      </button>
      <button type="button" className={lang === "en" ? "is-active" : ""} onClick={() => setLang("en")}>
        EN
      </button>
    </div>
  );
}

const SCREENS = {
  profile: ProfileScreen,
  search: SearchScreen,
  vacancies: VacanciesScreen,
  confirm: ConfirmScreen,
  subscribe: SubscribeScreen,
};

const TAB_ORDER = ["profile", "search", "vacancies", "confirm", "subscribe"];

// variants-функции (а не голые initial/exit объекты) — обязательное условие,
// чтобы AnimatePresence прокидывал АКТУАЛЬНОЕ значение custom (direction) в
// exit-анимацию уже УХОДЯЩЕГО экрана. Без этого exit брал бы direction,
// который был на момент, когда этот экран сам ВОШЁЛ (устаревшее значение) —
// проверено напрямую (замерял computed transform по кадрам): при переходе
// назад уходящий экран всё равно улетал влево, как будто идём вперёд.
const screenVariants = {
  enter: (direction) => ({ opacity: 0, x: direction * 14 }),
  center: { opacity: 1, x: 0 },
  exit: (direction) => ({ opacity: 0, x: direction * -14 }),
};

// QR-код профиля (10.08.2026): бот открывает Mini App web_app-кнопкой на
// URL вида `<guro_id_webapp_url>/?target=<user_id>` (см. handlers/flow.py
// start()) — читаем ?target= ОДИН раз при старте приложения, до всякого
// React-состояния, чтобы решить стартовый таб ДО первого рендера.
function readDeepLinkTarget() {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("target");
}

// "Мой QR" кабинета Рекрутер (26.08.2026, ТЗ "Гуро рекрутер каб") — payload
// guro_<id>_r даёт боту ?target=<id>&workspace=recruiter (см. handlers/
// flow.py::start), сканирующий должен попасть сразу на РЕКРУТЕРСКУЮ
// карточку, не личный профиль.
function readDeepLinkWorkspace() {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("workspace");
}

// Уведомление о новом сообщении (Фаза 1, 11.08.2026, см. guro_id_api.py::
// _notify_new_message) открывает Mini App на `?thread=<sender_id>` — та же
// механика deep-link'а, что уже была у QR (?target=), только ведёт не в
// Поиск, а сразу в переписку внутри Профиля.
function readDeepLinkThread() {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("thread");
}

function AppShell() {
  const { t } = useLang();
  const [intro, setIntro] = useState(true);
  const initialTargetRef = useRef(readDeepLinkTarget());
  const initialWorkspaceRef = useRef(readDeepLinkWorkspace());
  const targetConsumedRef = useRef(false);
  const initialThreadRef = useRef(readDeepLinkThread());
  // messageTargetId — не только начальный deep-link, но и рантайм-переход
  // из кнопки "Написать" в поиске (см. openMessages ниже), поэтому это
  // обычный state, а не ref с отдельным consumed-флагом, как у ?target=.
  const [messageTargetId, setMessageTargetId] = useState(initialThreadRef.current);
  // "Подтвердить найм" из отклика на вакансию (26.08.2026, ТЗ "Recruitment —
  // ВАКАНСИИ", раздел 5.4) — вакансии живут в СВОЕЙ вкладке (не внутри
  // Профиля), поэтому переход в форму найма кабинета Рекрутер требует
  // межвкладочной передачи (та же механика, что openMessages/messageTargetId).
  const [hireConfirmPrefill, setHireConfirmPrefill] = useState(null);
  // Личный/Рекрутер/Компания (28.08.2026, фидбек владельца: "выбрал
  // Компанию, ушёл на Сделки — сбрасывает на Личный") — раньше жил ВНУТРИ
  // ProfileScreen как локальный useState, поэтому обнулялся при каждом
  // размонтировании (переключение таба размонтирует экран целиком, см.
  // key={tab} ниже). Здесь, в AppShell, компонент не размонтируется никогда
  // — значение переживает любое переключение табов. Заодно даёт табу
  // "Сделки" знать, от чьего лица действовать (см. confirmProps ниже) —
  // раньше эта вкладка вообще не подозревала о выборе воркспейса в Профиле.
  const [workspace, setWorkspace] = useState("personal");
  const [tab, setTab] = useState(initialTargetRef.current ? "search" : "profile");
  // Направление перехода между экранами — вперёд (вправо-налево, как
  // раньше) или назад (зеркально, влево-направо), в зависимости от того,
  // левее или правее текущего таб в TAB_ORDER тот, на который переключаемся.
  const [direction, setDirection] = useState(1);

  useEffect(() => {
    initTelegram();
    // Сразу чистим query string — иначе обновление/повторный заход в этот
    // же сеанс WebApp заново триггерил бы deep-link на каждый ре-маунт.
    if ((initialTargetRef.current || initialThreadRef.current) && window.history?.replaceState) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  function handleTabChange(next) {
    const oldIndex = TAB_ORDER.indexOf(tab);
    const newIndex = TAB_ORDER.indexOf(next);
    setDirection(newIndex >= oldIndex ? 1 : -1);
    setTab(next);
  }

  // Кнопка "Написать" на разблокированном профиле в Поиске — переключает на
  // вкладку Профиль и сразу открывает переписку с этим человеком.
  function openMessages(userId) {
    setMessageTargetId(String(userId));
    handleTabChange("profile");
  }

  function openHireConfirm(prefill) {
    setHireConfirmPrefill(prefill || {});
    handleTabChange("profile");
  }

  const Screen = SCREENS[tab];
  // Таб "Сделки" наследует контекст воркспейса (28.08.2026) — то же
  // соответствие, что уже было у точечных кнопок ВНУТРИ кабинетов
  // ("Подтвердить сделку/найм" в Компании -> asCompany, "Подтвердить найм"
  // в Рекрутере -> forcedType="hire"), просто теперь работает и с нижнего
  // таба, а не только из хаба конкретного кабинета.
  const confirmProps =
    tab !== "confirm" ? {} :
    workspace === "company" ? { asCompany: true } :
    workspace === "recruiter" ? { forcedType: "hire" } : {};

  return (
    <LayoutGroup>
      {/* Заставка со слот-барабанами "GURO ID" — каждая буква letit наверх
          в шапку СВОИМ layoutId (brandLetters.js), это ТЕ ЖЕ САМЫЕ буквы,
          что стояли в барабане, а не новый текстовый блок. */}
      <AnimatePresence>{intro && <SlotIntro key="intro" onDone={() => setIntro(false)} />}</AnimatePresence>

      {!intro && (
        <div className="app">
          <div className="header">
            <LanguageSwitch />
            <div className="brand">
              {BRAND_WORD_1.map((l) => (
                <motion.span key={l.id} layoutId={`brand-${l.id}`} className="brand-letter">
                  {l.char}
                </motion.span>
              ))}
              <span className="brand-letter-space"> </span>
              {BRAND_WORD_2.map((l) => (
                <motion.span key={l.id} layoutId={`brand-${l.id}`} className="brand-letter">
                  {l.char}
                </motion.span>
              ))}
            </div>
            <motion.div
              className="subtitle"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.3 }}
            >
              {t("app.subtitle")}
            </motion.div>
          </div>

          <div className="screen-viewport">
            <AnimatePresence mode="wait" custom={direction}>
              <motion.div
                key={tab}
                custom={direction}
                variants={screenVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.22, ease: "easeOut" }}
              >
                <Screen
                  onNavigate={handleTabChange}
                  workspace={workspace}
                  onWorkspaceChange={setWorkspace}
                  {...confirmProps}
                  deepLinkTargetId={
                    tab === "search" && initialTargetRef.current && !targetConsumedRef.current
                      ? initialTargetRef.current
                      : undefined
                  }
                  deepLinkWorkspace={initialWorkspaceRef.current || undefined}
                  onConsumeDeepLink={() => {
                    targetConsumedRef.current = true;
                  }}
                  onOpenMessages={openMessages}
                  messageTargetId={messageTargetId}
                  onConsumeMessageTarget={() => setMessageTargetId(null)}
                  onOpenHireConfirm={openHireConfirm}
                  hireConfirmPrefill={hireConfirmPrefill}
                  onConsumeHireConfirmPrefill={() => setHireConfirmPrefill(null)}
                />
              </motion.div>
            </AnimatePresence>
          </div>

          <TabBar active={tab} onChange={handleTabChange} />
        </div>
      )}
    </LayoutGroup>
  );
}

export default function App() {
  return (
    <LangProvider>
      <AppShell />
    </LangProvider>
  );
}
