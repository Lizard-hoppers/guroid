import { useState } from "react";
import { motion } from "framer-motion";
import { formatDate, initialOf } from "../utils.js";
import { setProfileField, setWorkStatus } from "../api.js";
import { haptic } from "../telegram.js";
import { useLang } from "../i18n.jsx";

// Статус трудоустройства (10.08.2026) — публичный маркер вроде "Open to
// Work" в LinkedIn, виден ВСЕМ бесплатно (даже без подписки), не тумблер
// приватности. 4-е состояние "выкл" = null, бейдж просто не рисуется.
export const WORK_STATUS_META = {
  looking: { emoji: "🟢", labelKey: "workStatus.looking" },
  neutral: { emoji: "❕", labelKey: "workStatus.neutral" },
  working: { emoji: "🔴", labelKey: "workStatus.working" },
};

export function WorkStatusBadge({ status }) {
  const { t } = useLang();
  const meta = WORK_STATUS_META[status];
  if (!meta) return null;
  return (
    <span className={`work-status-badge work-status-${status}`}>
      {meta.emoji} {t(meta.labelKey)}
    </span>
  );
}

// Сегментированный переключатель из 4 состояний (3 статуса + "Выкл") — для
// собственного профиля владельца. Каждый клик сразу шлёт POST на сервер
// (не требует отдельного "Сохранить", как EditableField — тут не текст,
// а закрытый выбор одного из вариантов).
export function WorkStatusPicker({ value, onChange }) {
  const { t } = useLang();
  const [saving, setSaving] = useState(false);

  async function pick(next) {
    if (saving || next === value) return;
    setSaving(true);
    try {
      const result = await setWorkStatus(next);
      onChange(result.work_status);
      haptic("select");
    } catch {
      haptic("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="work-status-picker">
      {Object.entries(WORK_STATUS_META).map(([key, meta]) => (
        <button
          key={key}
          type="button"
          className={`work-status-option${value === key ? " active" : ""}`}
          onClick={() => pick(key)}
          disabled={saving}
        >
          {meta.emoji} {t(meta.labelKey)}
        </button>
      ))}
      <button
        type="button"
        className={`work-status-option work-status-off${!value ? " active" : ""}`}
        onClick={() => pick(null)}
        disabled={saving}
      >
        {t("workStatus.off")}
      </button>
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
