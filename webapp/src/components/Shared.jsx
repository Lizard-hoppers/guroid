import { motion } from "framer-motion";
import { formatDate, initialOf } from "../utils.js";

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

export function PartnerRow({ partner }) {
  const displayName = partner.name || (partner.username ? `@${partner.username}` : "Без имени");
  return (
    <div className="partner-row">
      <div className="avatar-dot">{initialOf(partner.name, partner.username)}</div>
      <div className="partner-info">
        <div className="partner-name">{displayName}</div>
        <div className="partner-meta">
          {partner.username && partner.name ? `@${partner.username} · ` : ""}
          {formatDate(partner.confirmed_at)}
        </div>
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
