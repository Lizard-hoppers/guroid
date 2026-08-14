import { useEffect, useRef, useState } from "react";
import { motion, useAnimation } from "framer-motion";
import { formatDate, initialOf } from "../utils.js";
import { setProfileField, setWorkStatus } from "../api.js";
import { haptic } from "../telegram.js";
import { useLang } from "../i18n.jsx";

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

const WORK_STATUS_BLOB_FILL = {
  looking: "rgba(107, 191, 138, 0.22)",
  neutral: "rgba(255, 255, 255, 0.14)",
  working: "rgba(224, 101, 90, 0.22)",
};
const WORK_STATUS_BLOB_BORDER = {
  looking: "rgba(107, 191, 138, 0.55)",
  neutral: "rgba(212, 175, 55, 0.28)",
  working: "rgba(224, 101, 90, 0.55)",
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
    if (activeIndex === -1) {
      controls.start({ opacity: 0, scale: 0.85, transition: { duration: 0.15 } });
    } else {
      controls.start({ x: activeIndex * step, opacity: 1, scale: 1, transition: WOBBLE });
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
      <div className="value">{value === null || value === undefined ? "🔒" : value}</div>
      <div className="label">{label}</div>
    </div>
  );
}

export function MetricsRow({ reputation, partnerships, daysInCommunity }) {
  const { t } = useLang();
  return (
    <div className="metrics-row">
      <Metric label={t("metric.rating")} value={reputation} />
      <Metric label={t("metric.partnerships")} value={partnerships} />
      <Metric label={t("metric.daysInCommunity")} value={daysInCommunity} />
    </div>
  );
}

// Сводка рейтинга прямо на визитке (14.08.2026, по фидбеку владельца с
// разбором PDF от 11.08 — кружок с рейтингом и счётчик сделок были в
// исходном макете НА ГЛАВНОМ экране, редизайн 10.08 унёс их только внутрь
// "Мой рейтинг", теперь возвращаем сводку на хаб, полная версия остаётся в
// подэкране как была). Клик открывает "Мой рейтинг" — там же и подробный
// разбор "Как поднять рейтинг?".
// Просто кружок с числом — стоит рядом с аватаром в шапке визитки, узкий
// и не толкает имя/должность/компанию. Текстовая часть (счётчик сделок +
// подсказка) вынесена в RatingSummaryLine — отдельной строкой НА ВСЮ
// ширину карточки (14.08.2026: узкая колонка рядом с кружком ломала
// перенос текста на узких экранах — "0 подтверждённых сделок" наезжало на
// имя, выглядело неряшливо). Обе половины ведут в один и тот же onOpen.
export function RatingPreview({ reputation, onOpen }) {
  const { t } = useLang();
  const locked = reputation === null || reputation === undefined;
  return (
    <button type="button" className="rating-preview" onClick={onOpen}>
      <div className="rating-preview-circle">{locked ? t("hub.ratingLocked") : Math.round(reputation)}</div>
    </button>
  );
}

export function RatingSummaryLine({ reputation, partnerships, isSubscribed, onOpen }) {
  const { t } = useLang();
  const locked = reputation === null || reputation === undefined;
  const showHint = locked || !isSubscribed || (partnerships ?? 0) === 0;
  return (
    <button type="button" className="rating-summary-line" onClick={onOpen}>
      <span className="rating-summary-deals">
        {locked ? t("hub.dealsLocked") : t("hub.dealsConfirmed", { count: partnerships ?? 0 })}
      </span>
      {showHint && (
        <span className="rating-summary-hint">
          {" "}
          · {t("hub.lowRatingHint")} · {t("hub.lowRatingCta")}
        </span>
      )}
    </button>
  );
}

// Офер/отзыв — публичны всегда (Фаза 2, 11.08.2026): в этом и смысл
// счётчика сделок — проверить репутацию контакта. Суммы показывает
// бэкенд только если инициатор включил show при создании заявки
// (guro_id_api._profile_summary), поэтому здесь просто рендерим то, что
// пришло — без своей логики видимости.
export function PartnerRow({ partner }) {
  const { t } = useLang();
  const displayName = partner.name || (partner.username ? `@${partner.username}` : t("common.noName"));
  const hasAmount = partner.amount_received != null || partner.amount_paid != null;
  return (
    <div className="partner-row">
      <div className="avatar-dot">{initialOf(partner.name, partner.username)}</div>
      <div className="partner-info">
        <div className="partner-name">{displayName}</div>
        <div className="partner-meta">
          {partner.username && partner.name ? `@${partner.username} · ` : ""}
          {formatDate(partner.confirmed_at)}
          {partner.vertical ? ` · ${partner.vertical}` : ""}
          {partner.geo ? ` · ${partner.geo}` : ""}
        </div>
        {partner.offer && <div className="partner-offer">{partner.offer}</div>}
        {hasAmount && (
          <div className="partner-meta">
            {partner.amount_received != null && `${t("partner.amountReceived")}: $${partner.amount_received}`}
            {partner.amount_received != null && partner.amount_paid != null && " · "}
            {partner.amount_paid != null && `${t("partner.amountPaid")}: $${partner.amount_paid}`}
            {" "}
            {t("partner.amountNote")}
          </div>
        )}
        {partner.review && <div className="partner-review">«{partner.review}»</div>}
      </div>
      {!partner.counts_toward_rating && <span className="badge-unrated">{t("partner.notRated")}</span>}
    </div>
  );
}

export function PartnersList({ partners, emptyHint }) {
  if (!partners || partners.length === 0) {
    return <div className="partner-meta">{emptyHint}</div>;
  }
  return (
    <div>
      {partners.map((p, i) => (
        <motion.div
          key={`${p.user_id}-${p.confirmed_at}`}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: Math.min(i, 8) * 0.04, duration: 0.25 }}
        >
          <PartnerRow partner={p} />
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
export function EditableField({ field, label, placeholder, value, multiline, onSaved, saveField = setProfileField }) {
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
        <div className="editable-field-value">{value}</div>
      ) : (
        <div className="editable-field-empty">{t("common.notFilled")}</div>
      )}
      <button className="btn secondary" style={{ marginTop: 8 }} onClick={startEdit}>
        {value ? t("common.edit") : t("common.fill")}
      </button>
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
