import { useEffect, useRef, useState } from "react";
import { motion, useAnimation } from "framer-motion";
import { formatDate } from "../utils.js";
import { ApiError, deleteRating, ratePartnership, setProfileField, setWorkStatus } from "../api.js";
import { haptic } from "../telegram.js";
import { useLang } from "../i18n.jsx";
import { IconCheck, IconCross, IconInfo, IconLock, IconWarning } from "./Icons.jsx";

// Статус трудоустройства (10.08.2026) — публичный маркер вроде "Open to
// Work" в LinkedIn, виден ВСЕМ бесплатно (даже без подписки), не тумблер
// приватности. "выкл" = null, бейдж просто не рисуется.
// Переделано 15.08.2026 (фидбек владельца): раньше цвет статуса нёс только
// цветной эмодзи (🟢/❕/🔴), а сама кнопка/бейдж всегда были одинаково
// золотыми — владелец попросил ровно наоборот: без цветного эмодзи, цвет
// несёт сама кнопка/бейдж. Плюс отдельная кнопка "Выкл" (4-й равноправный
// вариант в сетке 2×2) убрана — теперь это один ряд из 3 сегментов, повтор
// тапа по уже активному снимает статус (см. WorkStatusPicker).
export const WORK_STATUS_META = {
  looking: { labelKey: "workStatus.looking" },
  neutral: { labelKey: "workStatus.neutral" },
  working: { labelKey: "workStatus.working" },
};

export function WorkStatusBadge({ status }) {
  const { t } = useLang();
  const meta = WORK_STATUS_META[status];
  if (!meta) return null;
  return (
    <span className={`work-status-badge work-status-${status}`}>
      {t(meta.labelKey)}
    </span>
  );
}

// 04.09.2026 — все три статуса одного цвета (лайм) по просьбе владельца:
// в сегментированном переключателе состояние и так читается позицией
// капли, разный цвет для "Уже работаю" был лишним.
const WORK_STATUS_BLOB_FILL = {
  looking: "rgba(170, 246, 74, 0.22)",
  neutral: "rgba(170, 246, 74, 0.22)",
  working: "rgba(170, 246, 74, 0.22)",
};
const WORK_STATUS_BLOB_BORDER = {
  looking: "rgba(170, 246, 74, 0.55)",
  neutral: "rgba(170, 246, 74, 0.55)",
  working: "rgba(170, 246, 74, 0.55)",
};

// Та же мягкая пружина, что у капли в таббаре (TabBar.jsx, WOBBLE) — один
// едва заметный лёгкий проскок при переключении, без дребезга. Переиспользую
// готовое значение, а не подбираю заново — оно уже несколько раз докручено
// по фидбеку владельца именно до "чуть покачивается, не сильно".
const WOBBLE = { type: "spring", stiffness: 280, damping: 28, mass: 1 };

// Сегментированный переключатель — один ряд из 3 статусов (для собственного
// профиля владельца). Каждый клик сразу шлёт POST на сервер (не требует
// отдельного "Сохранить", как EditableField — тут не текст, а закрытый
// выбор одного из вариантов). Повторный тап по уже активному сегменту
// снимает статус — отдельная кнопка "Выкл" не нужна (15.08.2026: убрана и
// текстовая ссылка "Выключить", которая была под рядом — владелец счёл её
// лишней, раз то же самое делает повторный тап).
//
// 15.08.2026 (второй заход): вместо мгновенной смены фона кнопки — capля-
// подложка, которая переезжает между сегментами с лёгким покачиванием (тот
// же приём, что и в TabBar.jsx, но БЕЗ drag — тут выбор всегда кликом, не
// перетаскиванием). pointer-events:none на капле — клики идут сквозь неё
// прямо на кнопки, она чисто визуальная. ПРЕДЫДУЩАЯ версия (мгновенная
// смена фона кнопки, без анимации) — commit be745bd, откат одной командой
// `git revert`, если новый вариант не понравится.
export function WorkStatusPicker({ value, onChange }) {
  const { t } = useLang();
  const [saving, setSaving] = useState(false);
  const barRef = useRef(null);
  const [segWidth, setSegWidth] = useState(0);
  // step (расстояние МЕЖДУ сегментами) ≠ segWidth (ширина ОДНОГО сегмента) —
  // между кнопками есть gap (styles.css), меряем реальное смещение по
  // offsetLeft соседних кнопок, а не просто ширину/3, иначе капля так же
  // накапливала бы ошибку от сегмента к сегменту, как раньше было с
  // .tab-blob в TabBar.jsx (тот же баг, тот же фикс).
  const [step, setStep] = useState(0);
  const controls = useAnimation();
  const keys = Object.keys(WORK_STATUS_META);
  const activeIndex = keys.indexOf(value);
  // Первое позиционирование капли (открытие вкладки Профиль/загрузка
  // анкеты) не должно анимироваться пружиной — иначе выглядит так, будто
  // статус только что переключился сам собой (фидбек владельца
  // 28.08.2026: "анимация переключения в статусе срабатывает" при
  // загрузке экрана). WOBBLE-пружина остаётся только для РЕАЛЬНОГО
  // клика пользователя — см. settledRef ниже.
  const settledRef = useRef(false);

  useEffect(() => {
    function measure() {
      const els = barRef.current?.querySelectorAll(".work-status-option");
      if (!els || els.length === 0) return;
      setSegWidth(els[0].offsetWidth);
      setStep(els.length > 1 ? els[1].offsetLeft - els[0].offsetLeft : els[0].offsetWidth);
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  useEffect(() => {
    if (!segWidth) return;
    const target =
      activeIndex === -1
        ? { opacity: 0, scale: 0.85 }
        : { x: activeIndex * step, opacity: 1, scale: 1 };
    if (!settledRef.current) {
      controls.set(target);
      settledRef.current = true;
    } else {
      controls.start({ ...target, transition: activeIndex === -1 ? { duration: 0.15 } : WOBBLE });
    }
  }, [activeIndex, segWidth, step, controls]);

  async function setStatus(target) {
    if (saving) return;
    setSaving(true);
    try {
      const result = await setWorkStatus(target);
      onChange(result.work_status);
      haptic("select");
    } catch {
      haptic("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="work-status-picker" ref={barRef}>
        {segWidth > 0 && (
          <motion.div
            className="work-status-blob"
            style={{
              width: segWidth,
              background: activeIndex >= 0 ? WORK_STATUS_BLOB_FILL[value] : "transparent",
              borderColor: activeIndex >= 0 ? WORK_STATUS_BLOB_BORDER[value] : "transparent",
            }}
            initial={false}
            animate={controls}
          />
        )}
        {Object.entries(WORK_STATUS_META).map(([key, meta]) => (
          <button
            key={key}
            type="button"
            className={`work-status-option work-status-${key}${value === key ? " active" : ""}`}
            onClick={() => setStatus(value === key ? null : key)}
            disabled={saving}
          >
            {t(meta.labelKey)}
          </button>
        ))}
      </div>
    </div>
  );
}

// "Раскрыт ли тариф оплаты" переживает перезагрузку мини-аппа (12.09.2026)
// — openTelegramLink (крипто-оплата) уводит из приложения, при возврате
// Telegram может перезагрузить WebView с нуля, и обычный useState(false)
// стирался бы, снова пряча кнопки оплаты за тизер-карточкой, хотя человек
// уже начал оплачивать и просто ещё не завершил.
export function usePersistentReveal(key) {
  const [value, setValue] = useState(() => {
    try {
      return localStorage.getItem(key) === "1";
    } catch {
      return false;
    }
  });
  function reveal() {
    setValue(true);
    try {
      localStorage.setItem(key, "1");
    } catch {
      // приватный режим / хранилище недоступно — раскрытие просто не переживёт reload
    }
  }
  return [value, reveal];
}

export function Msg({ type = "error", children }) {
  if (!children) return null;
  return <div className={`msg ${type}`}>{children}</div>;
}

export function Spinner({ children }) {
  return <div className="spinner">{children}</div>;
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <div className="value">
        {value === null || value === undefined ? <IconLock /> : value}
      </div>
      <div className="label">{label}</div>
    </div>
  );
}

export function MetricsRow({ reputation, partnerships, daysInCommunity, showVisibilityHint = false }) {
  const { t } = useLang();
  return (
    <>
      <div className="metrics-row">
        <Metric label={t("metric.rating")} value={reputation} />
        <Metric label={t("metric.partnerships")} value={partnerships} />
        <Metric label={t("metric.daysInCommunity")} value={daysInCommunity} />
      </div>
      {showVisibilityHint && (
        <div className="hint-block">
          <IconLock /> {t("identity.visibilityHint")}
        </div>
      )}
    </>
  );
}

// Кружок рейтинга кабинета "Рекрутер" (28.08.2026, макет "11 · Рекрутер —
// главный экран") — раньше был общим с личным профилем, тот же компонент
// красился по вердикту 0/1-4/5+ (устаревшие пороги ЕЩЁ линейной формулы
// рейтинга ДО v2, см. git-историю). Личный профиль с тех пор переехал на
// RatingCard (см. ниже) — тут остался ЕДИНСТВЕННЫЙ потребитель
// (RecruiterHub.jsx), поэтому цветовые пороги убраны совсем: просто
// бирюзовое кольцо (--recruiter-cyan), тот же акцент, что у аватара/
// бейджа "HR"/вертикали в этом кабинете — макет не красит кружок по
// значению рейтинга вообще.
export function RatingPreview({ reputation, onOpen }) {
  const { t } = useLang();
  const locked = reputation === null || reputation === undefined;
  return (
    <button type="button" className="rating-preview" onClick={onOpen}>
      <div className="rating-preview-circle">
        {locked ? <IconLock /> : Math.round(reputation)}
      </div>
    </button>
  );
}

// Карточка рейтинга на главном экране Профиля (28.08.2026, макет "01 ·
// Профиль (личный)") — заменяет прежний маленький кружок в шапке визитки
// (RatingPreview выше, остался как был, но только для кабинета
// "Рекрутер"). Кольцо-прогресс 0-100 + название уровня из
// reputation_tier — бэкенд шлёт Bronze/Silver/Gold/Platinum уже с
// 25.08.2026 (формула рейтинга v2, см. guro_logic.reputation_tier),
// фронт эти поля просто не использовал до сих пор.
const RATING_TIER_LABEL_KEY = {
  Bronze: "rating.tier.bronze",
  Silver: "rating.tier.silver",
  Gold: "rating.tier.gold",
  Platinum: "rating.tier.platinum",
};

const RATING_RING_RADIUS = 46;
const RATING_RING_STROKE = 8;
const RATING_RING_CIRCUMFERENCE = 2 * Math.PI * RATING_RING_RADIUS;

export function RatingCard({ reputation, tier, partnerships, daysInCommunity }) {
  const { t } = useLang();
  const score = reputation ?? 0;
  const pct = Math.max(0, Math.min(1, score / 100));
  const offset = RATING_RING_CIRCUMFERENCE * (1 - pct);
  const tierLabelKey = RATING_TIER_LABEL_KEY[tier] || RATING_TIER_LABEL_KEY.Bronze;

  return (
    <div className="card rating-card">
      <div className="rating-card-head">
        <span className="section-eyebrow">{t("hub.ratingCard.title")}</span>
        <span className="rating-card-score">{Math.round(score)} / 100</span>
      </div>
      <div className="rating-card-body">
        <div className="rating-ring-wrap">
          <svg className="rating-ring" viewBox="0 0 120 120">
            <circle className="rating-ring-track" cx="60" cy="60" r={RATING_RING_RADIUS} strokeWidth={RATING_RING_STROKE} fill="none" />
            <circle
              className="rating-ring-progress"
              cx="60"
              cy="60"
              r={RATING_RING_RADIUS}
              strokeWidth={RATING_RING_STROKE}
              fill="none"
              strokeDasharray={RATING_RING_CIRCUMFERENCE}
              strokeDashoffset={offset}
              strokeLinecap="round"
              transform="rotate(-90 60 60)"
            />
          </svg>
          <div className="rating-ring-value">{Math.round(score)}</div>
        </div>
        <div className="rating-card-info">
          <div className="rating-card-tier">{t(tierLabelKey)}</div>
          <div className="rating-card-hint">{t("hub.ratingCard.hint")}</div>
        </div>
      </div>
      <div className="metrics-row rating-card-metrics">
        <div className="metric">
          <div className="value">{partnerships ?? 0}</div>
          <div className="label">{t("hub.ratingCard.partnerships")}</div>
        </div>
        <div className="metric">
          <div className="value">{daysInCommunity ?? 0}</div>
          <div className="label">{t("hub.ratingCard.tenure")}</div>
        </div>
      </div>
    </div>
  );
}

// Оценка партнёрства, Шаг 2 (ТЗ 6.1, 25.08.2026) — своя оценка (my_rating)
// не меняется после отправки, чужая (other_rating) приходит от бэкенда
// ТОЛЬКО когда обе стороны оценили или истёк таймаут (rating_revealed) —
// anti-retaliation целиком на бэкенде, тут просто рендерим то, что пришло.
const RATING_META = {
  // Icon вместо emoji (07.09.2026, дизайн-система, раздел 6): один смысл —
  // одна иконка, и в тексте, и в чипе рисуется одним набором.
  success: { Icon: IconCheck, color: "var(--gold)", labelKey: "rating.verdict.success" },
  nuance: { Icon: IconWarning, color: "var(--amber)", labelKey: "rating.verdict.nuance" },
  problematic: { Icon: IconCross, color: "var(--danger)", labelKey: "rating.verdict.problematic" },
};

// onCancel передан только в РЕЖИМЕ РЕДАКТИРОВАНИЯ уже поставленной оценки
// (25.08.2026, фидбек владельца "Правки.pdf" — "добавить возможность
// удаления, редактирования") — при первой оценке отменять нечего.
function RateWidget({ partnershipId, onRated, onCancel }) {
  const { t } = useLang();
  const [pendingComment, setPendingComment] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(verdict, text) {
    setBusy(true);
    setError(null);
    try {
      await ratePartnership(partnershipId, verdict, text);
      haptic("success");
      onRated(verdict);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "ERROR");
      haptic("error");
    } finally {
      setBusy(false);
    }
  }

  if (pendingComment) {
    return (
      <div className="rate-widget">
        <textarea
          rows={2}
          placeholder={t("rating.commentPlaceholder")}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
        <button className="btn" disabled={busy} onClick={() => submit("problematic", comment)}>
          {t("rating.commentSubmit")}
        </button>
      </div>
    );
  }

  return (
    <div className="rate-widget">
      <div className="partner-meta">{t("rating.ratePrompt")}</div>
      <div className="rate-widget-buttons">
        <button type="button" disabled={busy} onClick={() => submit("success")}>
          <IconCheck style={{ color: "var(--gold)" }} /> {t("rating.verdict.success")}
        </button>
        <button type="button" disabled={busy} onClick={() => submit("nuance")}>
          <IconWarning style={{ color: "var(--amber)" }} /> {t("rating.verdict.nuance")}
        </button>
        <button type="button" disabled={busy} onClick={() => setPendingComment(true)}>
          <IconCross style={{ color: "var(--danger)" }} /> {t("rating.verdict.problematic")}
        </button>
      </div>
      {onCancel && (
        <button type="button" className="onboarding-more-link" onClick={onCancel} style={{ marginTop: 8 }}>
          <span className="link-underline">{t("common.cancel")}</span>
        </button>
      )}
      {error && <Msg type="error">{t("rating.error")}</Msg>}
    </div>
  );
}

// Офер/отзыв — публичны всегда (Фаза 2, 11.08.2026): в этом и смысл
// счётчика сделок — проверить репутацию контакта. Суммы показывает
// бэкенд только если инициатор включил show при создании заявки
// (guro_id_api._profile_summary), поэтому здесь просто рендерим то, что
// пришло — без своей логики видимости. allowRating (25.08.2026) — ТОЛЬКО
// для списка СВОИХ партнёрств (RatingSubscreen) — просмотр чужого списка
// через SearchScreen никогда не показывает кнопки оценки (не участник сделки).
// Зона загрузки картинки из галереи (28.08.2026; 05.09.2026 вынесена сюда
// из CompanyHub — тем же компонентом грузится логотип кабинета Рекрутер).
// Сама функция загрузки приходит пропом `upload`: у компании это
// uploadCompanyImage со своим видом (logo/cover), у рекрутера —
// uploadRecruiterImage, вид там всегда один.
// Обёрнутый children кликабелен целиком (и пустое состояние, и уже
// загруженная картинка — заменить тоже можно тапом), input[type=file]
// спрятан рядом. Подсказка про формат/размер — ОТДЕЛЬНЫМ текстом под
// зоной: сама зона тесная, надпись внутри неё нечитаема.
export function ImageUploadArea({ upload, className, hintKey, onUploaded, onError, children, wrap = true }) {
  const { t } = useLang();
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function onFileChange(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const extra = await upload(file);
      onUploaded(extra);
      haptic("success");
    } catch (err) {
      const code = err instanceof ApiError ? err.code : null;
      const message =
        code === "FILE_TOO_LARGE" ? t("company.upload.tooLarge") :
        code === "UNSUPPORTED_FORMAT" ? t("company.upload.unsupported") :
        t("company.upload.error");
      if (onError) onError(message);
      else setError(message);
      haptic("error");
    } finally {
      setBusy(false);
    }
  }

  // Нативная связка label -> input вместо программного inputRef.click()
  // (06.09.2026, «компания.pdf», стр. 1: «выбрал файл — выкинуло из
  // приложения»). Синтетический клик по спрятанному display:none инпуту
  // разрывает цепочку пользовательской активации, вебвью Telegram теряет
  // фокус и сворачивает мини-приложение. По клику по label выборщик
  // открывает сам браузер, JS в цепочке нет.
  const trigger = (
    <>
      <label className={`${className}${busy ? " is-uploading" : ""} upload-trigger`}>
        {children}
        {/* Не display:none: так инпут выпадает из дерева отрисовки, и часть
            движков перестаёт его активировать по label. Прячем размером. */}
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="upload-input"
          disabled={busy}
          onChange={onFileChange}
        />
      </label>
    </>
  );

  if (!wrap) return trigger;
  return (
    <div>
      {trigger}
      {hintKey && <p className="partner-meta company-upload-hint">{t(hintKey)}</p>}
      {error && <Msg type="error">{error}</Msg>}
    </div>
  );
}

// Ссылка на транзакцию в эксплорере (ТЗ раздел 6). Для известных сетей —
// прямо на страницу транзакции, иначе универсальный поиск blockchair.
const TX_EXPLORERS = {
  tron: (h) => `https://tronscan.org/#/transaction/${h}`,
  ethereum: (h) => `https://etherscan.io/tx/${h}`,
  bsc: (h) => `https://bscscan.com/tx/${h}`,
};

function explorerUrl(network, hash) {
  const build = TX_EXPLORERS[network];
  return build ? build(hash) : `https://blockchair.com/search?q=${encodeURIComponent(hash)}`;
}

// Многоточие ПОСЕРЕДИНЕ: хвост хеша так же важен для сверки глазами, как и
// начало, поэтому обычный overflow с обрезкой справа тут не годится.
function shortHash(hash) {
  return hash.length <= 24 ? hash : `${hash.slice(0, 10)}…${hash.slice(-10)}`;
}

// Три состояния проверки + сам хеш (ТЗ разделы 2, 6, 10, 11).
function TxVerification({ partner }) {
  const { t } = useLang();
  const [copied, setCopied] = useState(false);
  const declared = partner.amount_received ?? partner.amount_paid ?? null;
  const hasAmount = declared !== null;
  // У безоплатного партнёрства состояния нет — писать «сумма со слов
  // сторон» не о чем. Суммы скрыты приватностью — тоже молчим.
  if (!hasAmount) return null;

  const state = partner.tx_state || "none";

  async function copyHash() {
    try {
      await navigator.clipboard.writeText(partner.tx_hash);
      setCopied(true);
      haptic("light");
      setTimeout(() => setCopied(false), 1500);
    } catch {
      haptic("error");
    }
  }

  return (
    <div className="tx-block">
      {state === "verified" && (
        <div className="tx-state tx-state--verified">
          <IconCheck /> {t("partner.tx.verified")}
        </div>
      )}
      {state === "mismatch" && (
        <div className="tx-state tx-state--mismatch">
          <div>
            <IconWarning /> {t("partner.tx.mismatch")}
          </div>
          <div className="tx-state-amounts">
            {t("partner.tx.declared")}: ${declared}
            {partner.tx_amount != null ? ` · ${t("partner.tx.onchain")}: $${partner.tx_amount}` : ""}
          </div>
        </div>
      )}
      {state === "none" && (
        <div className="tx-state tx-state--none">
          {/* Без этой оговорки состояние выглядит необъяснимым: хеш
              приложен, транзакция настоящая, сумма сходится — а
              подтверждения нет (ТЗ «Hash_Uniqueness», раздел 5). */}
          {partner.tx_verify_error === "TX_TOO_OLD"
            ? t("partner.tx.tooOld")
            : t("partner.tx.none")}
        </div>
      )}

      {partner.tx_hash && (
        <div className="tx-hash-row">
          <span className="tx-hash-value">{shortHash(partner.tx_hash)}</span>
          <button type="button" className="tx-hash-copy" onClick={copyHash}>
            {copied ? t("partner.tx.copied") : t("partner.tx.copy")}
          </button>
        </div>
      )}
      {partner.tx_hash && (
        <a
          className="tx-explorer-link"
          href={explorerUrl(partner.tx_network, partner.tx_hash)}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t("partner.tx.explorer")}
        </a>
      )}
    </div>
  );
}

export function PartnerRow({ partner, allowRating = false }) {
  const { t } = useLang();
  const [myRating, setMyRating] = useState(partner.my_rating);
  const [editingRating, setEditingRating] = useState(false);
  const [deletingRating, setDeletingRating] = useState(false);
  // "Анонимная сделка" (11.09.2026): identity_visible===false значит ЭТОТ
  // смотрящий — третье лицо, бэкенд уже обнулил user_id/username/name
  // (guro_id_api._scrub_anonymous_partners). Отдельная метка "Аноним", а
  // не общий t("common.noName") — тот про "имя не заполнено", это про
  // "имя нарочно скрыто", разные ситуации для читающего.
  const isAnonymous = partner.identity_visible === false;
  const displayName = isAnonymous
    ? t("partner.anonymous")
    : partner.name || (partner.username ? `@${partner.username}` : t("common.noName"));

  // Удаление своей оценки (25.08.2026, фидбек владельца "Правки.pdf":
  // "удалить может тот, кто отзыв оставил") — сразу пересчитывает рейтинг
  // контрагента на бэкенде, если партнёрство уже было раскрыто.
  async function handleDeleteRating() {
    setDeletingRating(true);
    try {
      await deleteRating(partner.id);
      haptic("success");
      setMyRating(null);
    } catch {
      haptic("error");
    } finally {
      setDeletingRating(false);
    }
  }
  const hasAmount = partner.amount_received != null || partner.amount_paid != null;
  const otherMeta = partner.other_rating ? RATING_META[partner.other_rating] : null;

  // Атрибуция оффера/отзыва (25.08.2026, баг из "Пофиксить.pdf": Артём
  // инициировал партнёрство и написал офер/отзыв О СЕБЕ ("прошёл обучение
  // у Юли"), но в СВОЁМ списке партнёрств это отображалось безлико под
  // именем Юли — читалось, будто ОНА проходила обучение у него. Офер/отзыв
  // всегда пишет ИНИЦИАТОР партнёрства (см. guro_id_api.handle_create_
  // partnership) — partner.user_id это ВСЕГДА собеседник (не владелец
  // списка), поэтому "инициатор == partner.user_id" однозначно говорит,
  // что слова принадлежат ИМЕННО ЕМУ, а не владельцу списка, независимо от
  // того, чей это список (свой — allowRating=true, или чужой через поиск).
  // user_id обнулён у анонимных записей — сравнение с initiator_id
  // всегда даст false, что здесь и нужно: атрибуцию "чьи это слова" по
  // анонимной личности не построить, откатываемся на общую формулировку.
  const partnerInitiated = !isAnonymous && partner.initiator_id === partner.user_id;
  const wordsLabel = partnerInitiated
    ? t("partner.wordsOf", { name: displayName })
    : (allowRating ? t("partner.wordsYours") : t("partner.wordsInitiator"));

  return (
    <div className={`partner-row${myRating ? ` partner-row--${myRating}` : ""}`}>
      {/* Шапка карточки: слева имя и мета, справа — бейдж своей оценки
          (макет "07 · История партнёрств"). Раньше оценка шла строкой
          "Моя оценка: …" внутри тела, а слева стояла аватарка-кружок,
          которой в макете нет. */}
      <div className="partner-row-head">
        <div className="partner-info">
          <div className="partner-name">{displayName}</div>
          <div className="partner-meta">
            {partner.username && partner.name ? `@${partner.username} · ` : ""}
            {formatDate(partner.confirmed_at)}
            {partner.ptype === "hire" ? ` · ${t("confirm.ptype.hire")}` : ""}
            {partner.vertical ? ` · ${partner.vertical}` : ""}
            {partner.geo ? ` · ${partner.geo}` : ""}
          </div>
        </div>
        {myRating && !editingRating && (
          <span className={`partner-verdict partner-verdict--${myRating}`}>
            {(() => {
              const { Icon, color } = RATING_META[myRating];
              return <Icon style={{ color }} />;
            })()}{" "}
            {t(RATING_META[myRating].labelKey)}
          </span>
        )}
        {!partner.counts_toward_rating && (
          <span className="badge-unrated">{t("partner.notRated")}</span>
        )}
      </div>
        {partner.offer && (
          <div className="partner-offer">
            <span className="partner-words-label">{wordsLabel}: </span>
            {partner.offer}
          </div>
        )}
        {hasAmount && (
          <div className="partner-meta">
            {partner.amount_received != null && `${t("partner.amountReceived")}: $${partner.amount_received}`}
            {partner.amount_received != null && partner.amount_paid != null && " · "}
            {partner.amount_paid != null && `${t("partner.amountPaid")}: $${partner.amount_paid}`}
            {" "}
            {t("partner.amountNote")}
          </div>
        )}
        {/* Хэш транзакции (16.08.2026) — привязан к той же видимости, что
            сумма (amount_visible на бэкенде, guro_id_api._profile_summary) —
            это подтверждение именно суммы, отдельного тумблера не заводили. */}
        <TxVerification partner={partner} />
        {/* review — legacy-поле (см. handle_create_partnership, 25.08.2026:
            новые сделки его больше не собирают), но старые записи ещё
            встречаются и несут ту же атрибуцию (писал ИНИЦИАТОР). */}
        {partner.review && (
          <div className="partner-review">
            <span className="partner-words-label">{wordsLabel}: </span>
            «{partner.review}»
          </div>
        )}
        {/* Сам вердикт теперь в бейдже шапки — тут остаются только действия. */}
        {myRating && !editingRating && allowRating && (
          <div className="partner-row-actions">
            <button type="button" className="rate-inline-link" onClick={() => setEditingRating(true)}>
              {t("rating.editLink")}
            </button>
            {" · "}
            <button
              type="button"
              className="rate-inline-link rate-inline-link--danger"
              disabled={deletingRating}
              onClick={handleDeleteRating}
            >
              {t("rating.deleteLink")}
            </button>
          </div>
        )}
        {otherMeta && (
          <div className="partner-offer">
            <span className="partner-words-label">{t("rating.otherRating")}:</span>
            <otherMeta.Icon style={{ color: otherMeta.color }} /> {t(otherMeta.labelKey)}
            {partner.other_rating_comment && ` — «${partner.other_rating_comment}»`}
          </div>
        )}
        {/* 28.08.2026 (макет "08 · История партнёрств"): раньше при
            otherMeta===null эта строка молча пропадала — не различить
            "ещё не оценил, жду" от "оценил, просто нейтрально". Условие
            !rating_revealed отличает это от случая "окно 14 дней истекло,
            собеседник так и не оценил" — тогда сообщение было бы враньём. */}
        {myRating && !otherMeta && !partner.rating_revealed && (
          <div className="partner-meta">
          <IconLock /> {t("rating.otherHidden")}
        </div>
        )}
        {allowRating && (!myRating || editingRating) && (
          <RateWidget
            partnershipId={partner.id}
            onRated={(v) => { setMyRating(v); setEditingRating(false); }}
            onCancel={myRating ? () => setEditingRating(false) : null}
          />
        )}
    </div>
  );
}

// Счётчики оборота (ТЗ «Верификация транзакций», разделы 7-8, 12).
// В подтверждённую сумму попадают ТОЛЬКО сделки с проверенной ончейн
// транзакцией — накрутить такую цифру нельзя, не совершив реальный
// перевод на эту сумму. Заявленное без подтверждения идёт отдельной
// строкой и намеренно приглушено, чтобы не смешивалось с проверенным.
function formatMoney(value) {
  return `$${Math.round(value || 0).toLocaleString("ru-RU").replace(/\u00a0/g, " ")}`;
}

// Карточка "активации" кабинета (11.09.2026, макет "GURO ID · Типографика
// экранов" — единый паттерн для трёх вкладок Личный/Рекрутер/Компания,
// когда кабинет ещё не создан/не оплачен): текущее пустое состояние,
// объяснение пользы, живой пример "после активации" с реальными цифрами
// масштаба, приватность-подсказка, цена и большая кнопка.
//
// Кнопка НЕ покупает подписку сама — она открывает уже существующий
// SubscribeScreen (месяц/год, крипта/звёзды, скидка первого дня) ниже.
// Так весь платёжный функционал остаётся в одном месте, а эта карточка —
// просто витрина-тизер перед ним (подтверждено владельцем 11.09.2026).
export function ActivationPreview({
  title,
  nowAvatar, nowName, nowSub, nowBadge,
  aboutText,
  exampleAvatar, exampleName, exampleSub, exampleBadge,
  stat1Label, stat1Value, stat2Label, stat2Value,
  metaLine,
  lockText, lockInfoText,
  priceLabel, priceValue,
  ctaLabel, onActivate,
}) {
  const { t } = useLang();
  // 11.09.2026, макет "GURO ID mobile app design (3)", пункт 9: короткий
  // заголовок + бабл-пояснение по тапу на "i" вместо постоянного абзаца в
  // карточке. На узком экране бабл раскрывается ПОД заголовком (в потоке),
  // а не сбоку, как на широком холсте презентации — там сбоку просто было
  // место, а не отдельное требование к геометрии.
  const [aboutOpen, setAboutOpen] = useState(false);
  // Приватность-подсказка (12.09.2026, макет Figma node 372-5077) —
  // отдельная от aboutOpen, только на вкладке Личный (lockInfoText не
  // передаётся у Рекрутера/Компании -> кнопка там не рендерится вообще).
  const [lockInfoOpen, setLockInfoOpen] = useState(false);
  return (
    <div className="card activation-preview">
      <div className="activation-title-row">
        <h3>{title}</h3>
        <button
          type="button"
          className="activation-info-btn"
          aria-label={t("activation.infoAria")}
          onClick={() => setAboutOpen((v) => !v)}
        >
          <IconInfo size={20} />
        </button>
      </div>
      {aboutOpen && <div className="activation-bubble">{aboutText}</div>}

      <div className="section-eyebrow" style={{ marginTop: 12 }}>{t("activation.nowLabel")}</div>
      <div className="activation-box">
        <div className="profile-header-card activation-now">
          <div className="profile-avatar-fallback activation-now-avatar">{nowAvatar}</div>
          <div className="profile-header-info">
            <h2 className="onboarding-mock-placeholder">{nowName}</h2>
            <div className="profile-header-sub onboarding-mock-placeholder">{nowSub}</div>
          </div>
          {nowBadge != null && <div className="rating-preview-circle activation-badge-dim">{nowBadge}</div>}
        </div>
      </div>

      <div className="section-eyebrow" style={{ marginTop: 16 }}>{t("activation.exampleLabel")}</div>
      <div className="activation-box activation-box--highlight">
        <div className="profile-header-card">
          <div className="profile-avatar-fallback">{exampleAvatar}</div>
          <div className="profile-header-info">
            <h2>{exampleName}</h2>
            <div className="profile-header-sub">{exampleSub}</div>
          </div>
          <div className="rating-preview-circle">{exampleBadge}</div>
        </div>
      {/* recruiter-metric* — тот же класс, что уже верно показывает
          реальные метрики в Характеристике Рекрутера/Компании (число
          лаймовым НАД подписью). turnover-* тут не подходил — это класс
          другого компонента (TurnoverCard), где порядок обратный. */}
      <div className="recruiter-metrics-grid" style={{ marginTop: 12 }}>
        <div className="recruiter-metric">
          <div className="recruiter-metric-value">{stat1Value}</div>
          <div className="recruiter-metric-label">{stat1Label}</div>
        </div>
        <div className="recruiter-metric">
          <div className="recruiter-metric-value">{stat2Value}</div>
          <div className="recruiter-metric-label">{stat2Label}</div>
        </div>
      </div>
        <div className="activation-meta">{metaLine}</div>
      </div>

      <div className="activation-lock">
        <IconLock />
        <span>{lockText}</span>
        {lockInfoText && (
          <button
            type="button"
            className="activation-info-btn"
            aria-label={t("activation.infoAria")}
            onClick={() => setLockInfoOpen((v) => !v)}
          >
            <IconInfo size={16} />
          </button>
        )}
      </div>
      {lockInfoOpen && lockInfoText && <div className="activation-bubble">{lockInfoText}</div>}

      <div className="activation-price-row">
        <span className="section-eyebrow">{priceLabel}</span>
        <span className="activation-price-value">{priceValue}</span>
      </div>
      <button className="btn" onClick={onActivate}>{ctaLabel}</button>
    </div>
  );
}

export function TurnoverCard({ turnover }) {
  const { t } = useLang();
  if (!turnover) return null;
  const unverified = (turnover.unverified_received || 0) + (turnover.unverified_paid || 0);

  const empty = !turnover.received && !turnover.paid && !unverified;

  return (
    <div className="card">
      <h3>{t("turnover.title")}</h3>
      {/* Слово «ончейн» стоит здесь, а не у каждой цифры: оно объясняет
          природу обеих сумм разом и не рвёт узкую ячейку на две строки. */}
      <div className="turnover-hint">{t("turnover.hint")}</div>
      <div className="turnover-row">
        <TurnoverCell label={t("turnover.received")} value={turnover.received} />
        <TurnoverCell label={t("turnover.paid")} value={turnover.paid} />
      </div>
      {unverified > 0 && (
        <div className="turnover-unverified">
          {t("turnover.unverified", { amount: formatMoney(unverified) })}
        </div>
      )}
      {/* У новичка ноль будет всегда — подаём его как начало пути, а не как
          упрёк (ТЗ раздел 12). */}
      {empty && <div className="turnover-empty">{t("turnover.empty")}</div>}
    </div>
  );
}

function TurnoverCell({ label, value }) {
  const { t } = useLang();
  return (
    <div className="turnover-cell">
      <div className="turnover-label">{label}</div>
      <div className={`turnover-value${value ? "" : " turnover-value--zero"}`}>
        {formatMoney(value)}
      </div>
      {/* Пометка ровно у цифры — она объясняет, почему сумме можно верить.
          У нуля её нет: подтверждать нечего. */}
      {value > 0 && (
        <div className="turnover-note">
          <IconCheck /> {t("turnover.confirmed")}
        </div>
      )}
    </div>
  );
}

export function PartnersList({ partners, emptyHint, allowRating = false }) {
  if (!partners || partners.length === 0) {
    return <div className="partner-meta">{emptyHint}</div>;
  }
  return (
    <div>
      {partners.map((p, i) => (
        <motion.div
          key={p.id}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: Math.min(i, 8) * 0.04, duration: 0.25 }}
        >
          <PartnerRow partner={p} allowRating={allowRating} />
        </motion.div>
      ))}
    </div>
  );
}

// value === null -> владелец скрыл поле тумблером приватности (см.
// guro_id_api._apply_privacy — редактирует именно в null, не убирает ключ).
// value === undefined/"" -> поле просто не заполнено в анкете, строку не рисуем.
export function IdentityLine({ label, value }) {
  const { t } = useLang();
  if (value === null) {
    return (
      <div className="partner-meta">
        {label}
        <span className="hidden-value">{t("common.hidden")}</span>
      </div>
    );
  }
  if (!value) return null;
  return (
    <div className="partner-meta">
      {label}
      {value}
    </div>
  );
}

// saveField (Фаза 3, 12.08.2026) — по умолчанию личный профиль
// (setProfileField), RecruiterHub передаёт setRecruiterProfileField, чтобы
// переиспользовать этот же компонент для витрины рекрутера без дублирования.
export function EditableField({ field, label, placeholder, value, multiline, onSaved, saveField = setProfileField, renderValue }) {
  const { t } = useLang();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function startEdit() {
    setDraft(value || "");
    setError("");
    setEditing(true);
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      const updated = await saveField(field, draft.trim());
      onSaved(updated[field]);
      setEditing(false);
      haptic("success");
    } catch {
      setError(t("common.saveError"));
      haptic("error");
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    const InputTag = multiline ? "textarea" : "input";
    return (
      <div className="editable-field">
        <label>{label}</label>
        <InputTag
          type={multiline ? undefined : "text"}
          rows={multiline ? 4 : undefined}
          placeholder={placeholder}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          autoFocus
          disabled={saving}
        />
        <div className="editable-field-actions">
          <button className="btn" style={{ marginTop: 8 }} onClick={save} disabled={saving}>
            {saving ? t("common.saving") : t("common.save")}
          </button>
          <button
            className="btn secondary"
            style={{ marginTop: 8 }}
            onClick={() => setEditing(false)}
            disabled={saving}
          >
            {t("common.cancel")}
          </button>
        </div>
        <Msg type="error">{error}</Msg>
      </div>
    );
  }

  return (
    <div className="editable-field">
      <label>{label}</label>
      {value ? (
        <div className="editable-field-value">{renderValue ? renderValue(value) : value}</div>
      ) : (
        <div className="editable-field-empty">{t("common.notFilled")}</div>
      )}
      <button className="btn secondary" style={{ marginTop: 8 }} onClick={startEdit}>
        {value ? t("common.edit") : t("common.fill")}
      </button>
    </div>
  );
}

function CvRow({ label, value }) {
  if (!value) return null;
  return (
    <div className="cv-readonly-row">
      <div className="cv-readonly-label">{label}</div>
      <div className="cv-readonly-value">{value}</div>
    </div>
  );
}

// Структурный read-only показ CV — 16.08.2026, по прямому запросу
// владельца: заполненные поля CV нигде не отображались целиком ни самому
// владельцу ("посмотреть, как видят другие"), ни чужому смотрящему при
// поиске/по QR (SearchScreen.jsx рисовал только голое cv_text, остальные
// 12+ полей расширения "Моё CV" от 12.08 были только в форме редактирования,
// бэкенд их уже отдавал — не хватало именно фронтенд-показа). Один и тот
// же компонент переиспользуется в CvViewScreen (свой CV) и в ResultCard
// SearchScreen.jsx (чужой CV) — гейт видимости (show_cv/подписка) уже
// решается на уровне того, ЧТО передаётся в profile, тут просто рендер.
export function CvReadOnly({ profile }) {
  const { t } = useLang();
  const tri = (v) => (v === true ? t("common.yes") : v === false ? t("common.no") : null);
  const salary = profile.cv_salary_negotiable
    ? t("cv.salary.negotiableLabel")
    : profile.cv_salary_from != null || profile.cv_salary_to != null
      ? `${profile.cv_salary_from ?? "?"}–${profile.cv_salary_to ?? "?"} $`
      : null;
  const experience = profile.cv_experience || [];
  const hasAny =
    profile.cv_text || profile.cv_profession || profile.cv_location || profile.cv_verticals ||
    profile.cv_grade || tri(profile.cv_relocation_ready) || tri(profile.cv_polygraph_consent) ||
    salary || profile.cv_skills || profile.cv_languages || profile.cv_certifications || experience.length > 0;
  if (!hasAny) return null;

  return (
    <div className="card cv-readonly">
      <h3>{t("cv.title")}</h3>
      <CvRow label={t("cv.profession.label")} value={profile.cv_profession} />
      <CvRow label={t("cv.grade.title")} value={profile.cv_grade} />
      <CvRow label={t("cv.location.label")} value={profile.cv_location} />
      <CvRow label={t("cv.verticals.title")} value={profile.cv_verticals ? profile.cv_verticals.split(",").join(", ") : null} />
      <CvRow label={t("cv.label")} value={profile.cv_text} />
      <CvRow label={t("cv.salary.title")} value={salary} />
      <CvRow label={t("cv.relocation.title")} value={tri(profile.cv_relocation_ready)} />
      <CvRow label={t("cv.polygraph.title")} value={tri(profile.cv_polygraph_consent)} />
      <CvRow label={t("cv.skills.label")} value={profile.cv_skills} />
      <CvRow label={t("cv.languages.label")} value={profile.cv_languages} />
      <CvRow label={t("cv.certifications.label")} value={profile.cv_certifications} />
      {experience.length > 0 && (
        <div className="cv-readonly-row">
          <div className="cv-readonly-label">{t("cv.experience.title")}</div>
          {experience.map((e) => (
            <div key={e.id} className="cv-experience-entry-view">
              <div className="cv-experience-entry-title">
                {e.position}
                {e.company ? ` · ${e.company}` : ""}
              </div>
              <div className="partner-meta">
                {e.date_from || "?"} — {e.date_to || t("cv.experience.present")}
                {e.location ? ` · ${e.location}` : ""}
              </div>
              {e.description && <div className="partner-meta">{e.description}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// "Кабинет: Рекрутер" (28.08.2026, макеты "12 · Рекрутер — Поиск
// кандидатов" и "13 · Рекрутер — Вакансии") — маленький бейдж-подсказка
// в шапке экранов, которые открываются В КОНТЕКСТЕ кабинета рекрутера
// (в отличие от ProfileHub/RecruiterHub, эти экраны — общие табы нижней
// навигации, viewer может не помнить, что зашёл сюда "как рекрутер").
// null для "personal"/"company" — компания пока без своего макета этого
// бейджа, не придумываю цвет заранее.
export function WorkspaceCabinetBadge({ workspace }) {
  const { t } = useLang();
  if (workspace !== "recruiter") return null;
  return <span className="workspace-cabinet-badge">{t("workspace.badge.recruiter")}</span>;
}

// «Характеристика» (26.08.2026, по прямому запросу владельца — кнопка,
// доступная в КАЖДОМ профиле, открывает офферы ("Я ищу"/"Я полезен") + CV
// того, кто просматривается; видна только при полной, разблокированной
// подписчиком карточке (ResultCard уже гарантирует это условие, см.
// SearchScreen.jsx) — отдельного платного гейта тут не нужно, сама карточка
// уже за пейволлом. Тот же компонент используется и в СВОЁМ профиле
// (ProfileHub) — превью того, что увидит подписанный смотрящий.
export function CharacteristicButton({ profile }) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const hasOffers = !!(profile.looking_for || profile.offering);
  return (
    <div className="characteristic-wrap">
      <button
        type="button"
        className="btn outline-accent"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? t("characteristic.hide") : t("characteristic.button")}
      </button>
      {open && (
        <>
          <div className="card cv-readonly">
            <h3>{t("characteristic.offersTitle")}</h3>
            <CvRow label={t("offers.lookingForLabel")} value={profile.looking_for} />
            <CvRow label={t("offers.offeringLabel")} value={profile.offering} />
            {!hasOffers && <div className="partner-meta">{t("characteristic.emptyOffers")}</div>}
          </div>
          <CvReadOnly profile={profile} />
        </>
      )}
    </div>
  );
}

export function LockedOverlay({ children, onUnlock }) {
  const { t } = useLang();
  return (
    <div className="card locked-overlay">
      <div className="locked-content">{children}</div>
      <div className="locked-cta">
        <div>
          <strong>{t("locked.title")}</strong>
          <div className="privacy-summary-note">{t("locked.note")}</div>
        </div>
        <button className="btn" style={{ width: "auto", padding: "10px 20px" }} onClick={onUnlock}>
          {t("rating.subscribeCta")}
        </button>
      </div>
    </div>
  );
}
