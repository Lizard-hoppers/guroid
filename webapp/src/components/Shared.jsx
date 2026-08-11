import { useState } from "react";
import { motion } from "framer-motion";
import { formatDate, initialOf } from "../utils.js";
import { setProfileField, setWorkStatus } from "../api.js";
import { haptic } from "../telegram.js";

// Статус трудоустройства (10.08.2026) — публичный маркер вроде "Open to
// Work" в LinkedIn, виден ВСЕМ бесплатно (даже без подписки), не тумблер
// приватности. 4-е состояние "выкл" = null, бейдж просто не рисуется.
export const WORK_STATUS_META = {
  looking: { emoji: "🟢", label: "Ищу работу" },
  neutral: { emoji: "❕", label: "Нейтральный" },
  working: { emoji: "🔴", label: "Уже работаю" },
};

export function WorkStatusBadge({ status }) {
  const meta = WORK_STATUS_META[status];
  if (!meta) return null;
  return (
    <span className={`work-status-badge work-status-${status}`}>
      {meta.emoji} {meta.label}
    </span>
  );
}

// Сегментированный переключатель из 4 состояний (3 статуса + "Выкл") — для
// собственного профиля владельца. Каждый клик сразу шлёт POST на сервер
// (не требует отдельного "Сохранить", как EditableField — тут не текст,
// а закрытый выбор одного из вариантов).
export function WorkStatusPicker({ value, onChange }) {
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
          {meta.emoji} {meta.label}
        </button>
      ))}
      <button
        type="button"
        className={`work-status-option work-status-off${!value ? " active" : ""}`}
        onClick={() => pick(null)}
        disabled={saving}
      >
        Выкл
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
  return (
    <div className="metrics-row">
      <Metric label="Рейтинг" value={reputation} />
      <Metric label="Партнёрств" value={partnerships} />
      <Metric label="Дней в комьюнити" value={daysInCommunity} />
    </div>
  );
}

// Офер/отзыв — публичны всегда (Фаза 2, 11.08.2026): в этом и смысл
// счётчика сделок — проверить репутацию контакта. Суммы показывает
// бэкенд только если инициатор включил show при создании заявки
// (guro_id_api._profile_summary), поэтому здесь просто рендерим то, что
// пришло — без своей логики видимости.
export function PartnerRow({ partner }) {
  const displayName = partner.name || (partner.username ? `@${partner.username}` : "Без имени");
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
            {partner.amount_received != null && `Получено: $${partner.amount_received}`}
            {partner.amount_received != null && partner.amount_paid != null && " · "}
            {partner.amount_paid != null && `Оплачено: $${partner.amount_paid}`}
            {" (со слов инициатора)"}
          </div>
        )}
        {partner.review && <div className="partner-review">«{partner.review}»</div>}
      </div>
      {!partner.counts_toward_rating && <span className="badge-unrated">не влияет на рейтинг</span>}
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
  if (value === null) {
    return (
      <div className="partner-meta">
        {label}
        <span className="hidden-value">Скрыто</span>
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

// Поле профиля, которого нет в анкете бота (GC.EXTRA_PROFILE_FIELDS) —
// единственный способ его заполнить/поменять это прямо здесь, в отличие от
// полей анкеты (name/company/vertical и т.п.), те остаются read-only.
// saveField (Фаза 3, 12.08.2026) — по умолчанию личный профиль
// (setProfileField), RecruiterHub передаёт setRecruiterProfileField, чтобы
// переиспользовать этот же компонент для витрины рекрутера без дублирования.
export function EditableField({ field, label, placeholder, value, multiline, onSaved, saveField = setProfileField }) {
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
      setError("Не получилось сохранить. Попробуйте ещё раз.");
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
            {saving ? "Сохраняем…" : "Сохранить"}
          </button>
          <button
            className="btn secondary"
            style={{ marginTop: 8 }}
            onClick={() => setEditing(false)}
            disabled={saving}
          >
            Отмена
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
        <div className="editable-field-empty">не заполнено</div>
      )}
      <button className="btn secondary" style={{ marginTop: 8 }} onClick={startEdit}>
        {value ? "Изменить" : "Заполнить"}
      </button>
    </div>
  );
}

export function LockedOverlay({ children, onUnlock }) {
  return (
    <div className="card locked-overlay">
      <div className="locked-content">{children}</div>
      <div className="locked-cta">
        <div>
          <strong>Полная карточка профиля</strong>
          <div className="privacy-summary-note">
            Полный профиль, партнёры и история — по подписке GURO ID
          </div>
        </div>
        <button className="btn" style={{ width: "auto", padding: "10px 20px" }} onClick={onUnlock}>
          Оформить подписку
        </button>
      </div>
    </div>
  );
}
