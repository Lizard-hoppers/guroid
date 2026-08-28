import { useEffect, useRef, useState } from "react";
import { motion, useAnimation } from "framer-motion";
import { formatDate, initialOf } from "../utils.js";
import { ApiError, deleteRating, ratePartnership, setProfileField, setWorkStatus } from "../api.js";
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
// Цветовые пороги кружка (15.08.2026, по прямому запросу владельца —
// рейтинг теперь стартует с 0, а не с базовых 50, см. guro_constants.py):
// 0 = красный, 1-4 = жёлтый, 5+ = зелёный. Замок (нет подписки) — отдельный
// нейтральный золотой стиль, под цветовые пороги не попадает.
function ratingTier(value) {
  if (value <= 0) return "rep-red";
  if (value < 5) return "rep-yellow";
  return "rep-green";
}

export function RatingPreview({ reputation, onOpen }) {
  const { t } = useLang();
  const locked = reputation === null || reputation === undefined;
  const tierClass = locked ? "" : ` ${ratingTier(reputation)}`;
  return (
    <button type="button" className="rating-preview" onClick={onOpen}>
      <div className={`rating-preview-circle${tierClass}`}>{locked ? t("hub.ratingLocked") : Math.round(reputation)}</div>
    </button>
  );
}

export function RatingSummaryLine({ reputation, partnerships, isSubscribed, onOpen }) {
  const { t } = useLang();
  const locked = reputation === null || reputation === undefined;
  const showHint = locked || !isSubscribed || (partnerships ?? 0) === 0;
  // Подсказка "низкий рейтинг" красным при 0, как и кружок (15.08.2026,
  // владелец: "кружок должен орать что всё плохо, текст тоже должен быть
  // красный") — при locked оставляем нейтральный золотой, там это не
  // "у вас плохо", а "оформите подписку, чтобы увидеть".
  const hintTierClass = !locked ? ` ${ratingTier(reputation)}` : "";
  return (
    <button type="button" className="rating-summary-line" onClick={onOpen}>
      <span className="rating-summary-deals">
        {locked ? t("hub.dealsLocked") : t("hub.dealsConfirmed", { count: partnerships ?? 0 })}
      </span>
      {showHint && (
        <span className={`rating-summary-hint${hintTierClass}`}>
          {" "}
          · {t("hub.lowRatingHint")} · {t("hub.lowRatingCta")}
        </span>
      )}
    </button>
  );
}

// Карточка рейтинга на главном экране Профиля (28.08.2026, макет "01 ·
// Профиль (личный)") — заменяет прежний маленький кружок в шапке визитки
// (RatingPreview/RatingSummaryLine выше, они остаются как были для
// кабинета "Рекрутер"). Кольцо-прогресс 0-100 + название уровня из
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
  success: { emoji: "✅", labelKey: "rating.verdict.success" },
  nuance: { emoji: "⚠️", labelKey: "rating.verdict.nuance" },
  problematic: { emoji: "❌", labelKey: "rating.verdict.problematic" },
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
          ✅ {t("rating.verdict.success")}
        </button>
        <button type="button" disabled={busy} onClick={() => submit("nuance")}>
          ⚠️ {t("rating.verdict.nuance")}
        </button>
        <button type="button" disabled={busy} onClick={() => setPendingComment(true)}>
          ❌ {t("rating.verdict.problematic")}
        </button>
      </div>
      {onCancel && (
        <button type="button" className="onboarding-more-link" onClick={onCancel} style={{ marginTop: 6 }}>
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
export function PartnerRow({ partner, allowRating = false }) {
  const { t } = useLang();
  const [myRating, setMyRating] = useState(partner.my_rating);
  const [editingRating, setEditingRating] = useState(false);
  const [deletingRating, setDeletingRating] = useState(false);
  const displayName = partner.name || (partner.username ? `@${partner.username}` : t("common.noName"));

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
  const partnerInitiated = partner.initiator_id === partner.user_id;
  const wordsLabel = partnerInitiated
    ? t("partner.wordsOf", { name: displayName })
    : (allowRating ? t("partner.wordsYours") : t("partner.wordsInitiator"));

  return (
    <div className="partner-row">
      <div className="avatar-dot">{initialOf(partner.name, partner.username)}</div>
      <div className="partner-info">
        <div className="partner-name">{displayName}</div>
        <div className="partner-meta">
          {partner.username && partner.name ? `@${partner.username} · ` : ""}
          {formatDate(partner.confirmed_at)}
          {partner.ptype === "hire" ? ` · ${t("confirm.ptype.hire")}` : ""}
          {partner.vertical ? ` · ${partner.vertical}` : ""}
          {partner.geo ? ` · ${partner.geo}` : ""}
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
        {partner.tx_hash && (
          <div className="partner-meta partner-tx-hash">
            {t("partner.txHash")}: <span className="partner-tx-hash-value">{partner.tx_hash}</span>
            {partner.tx_verified ? ` · ${t("partner.txVerified")}` : ""}
          </div>
        )}
        {/* review — legacy-поле (см. handle_create_partnership, 25.08.2026:
            новые сделки его больше не собирают), но старые записи ещё
            встречаются и несут ту же атрибуцию (писал ИНИЦИАТОР). */}
        {partner.review && (
          <div className="partner-review">
            <span className="partner-words-label">{wordsLabel}: </span>
            «{partner.review}»
          </div>
        )}
        {myRating && !editingRating && (
          <div className="partner-meta">
            {t("rating.myRating")}: {RATING_META[myRating].emoji} {t(RATING_META[myRating].labelKey)}
            {allowRating && (
              <>
                {" · "}
                <button type="button" className="rate-inline-link" onClick={() => setEditingRating(true)}>
                  {t("rating.editLink")}
                </button>
                {" · "}
                <button
                  type="button"
                  className="rate-inline-link"
                  disabled={deletingRating}
                  onClick={handleDeleteRating}
                >
                  {t("rating.deleteLink")}
                </button>
              </>
            )}
          </div>
        )}
        {otherMeta && (
          <div className="partner-meta">
            {t("rating.otherRating")}: {otherMeta.emoji} {t(otherMeta.labelKey)}
            {partner.other_rating_comment && ` — «${partner.other_rating_comment}»`}
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
      {!partner.counts_toward_rating && <span className="badge-unrated">{t("partner.notRated")}</span>}
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
          key={`${p.user_id}-${p.confirmed_at}`}
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
    <div>
      <button
        type="button"
        className="btn secondary"
        style={{ marginTop: 8 }}
        onClick={() => setOpen((v) => !v)}
      >
        🪪 {open ? t("characteristic.hide") : t("characteristic.button")}
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
