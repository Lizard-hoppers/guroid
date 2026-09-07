import { useState } from "react";
import { ratePartnership, ApiError } from "../api.js";
import { Msg } from "./Shared.jsx";
import { haptic } from "../telegram.js";
import { useLang } from "../i18n.jsx";
import { IconCheck, IconCross, IconLock, IconWarning } from "./Icons.jsx";
import { formatDate } from "../utils.js";

// Оценка партнёрства, Шаг 2 из 2 (28.08.2026, макет "07 · Сделки — шаг 2
// (оценка)", Untitled-10) — отдельный экран, открывается из списка "Ждут
// вашей оценки" на табе "Подтвердить" (см. ConfirmScreen.jsx). Раньше
// оценка была маленьким виджетом внутри строки "Мой рейтинг"
// (RateWidget, Shared.jsx) — тот остаётся как есть (используется списком
// партнёрств), этот компонент — самостоятельный полноэкранный вариант.
const VERDICT_ERROR_KEYS = {
  COMMENT_REQUIRED: "confirm.rate.commentRequired",
  NOT_YOUR_PARTNERSHIP: "confirm.error.generic",
  NOT_CONFIRMED: "confirm.error.generic",
};

export function RatePartnershipScreen({ partnership, onBack, onDone }) {
  const { t } = useLang();
  const [verdict, setVerdict] = useState(null);
  const [comment, setComment] = useState("");
  const [state, setState] = useState({ loading: false, error: null });

  const heading = partnership.name || (partnership.username ? `@${partnership.username}` : t("common.noName"));

  async function onSubmit(e) {
    e.preventDefault();
    if (!verdict) return;
    if (verdict !== "success" && !comment.trim()) {
      setState({ loading: false, error: "COMMENT_REQUIRED" });
      return;
    }
    setState({ loading: true, error: null });
    try {
      await ratePartnership(partnership.id, verdict, comment.trim() || null);
      haptic("success");
      onDone();
    } catch (error) {
      setState({
        loading: false,
        error: error instanceof ApiError ? error.code : "generic",
      });
      haptic("error");
    }
  }

  const errorText = state.error
    ? t(VERDICT_ERROR_KEYS[state.error] || "confirm.error.generic")
    : null;

  return (
    <div className="card">
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <h3>{t("confirm.rate.title")}</h3>
      <div className="confirm-step-label">{t("confirm.rate.stepLabel")}</div>
      <div className="privacy-hint">{t("confirm.rate.hint")}</div>

      <label>{t("confirm.rate.partnershipLabel")}</label>
      <div className="confirm-rate-partnership-box">
        {heading}
        {partnership.username && partnership.name ? ` (@${partnership.username})` : ""}
        {" · "}
        {t(partnership.ptype === "hire" ? "confirm.ptype.hire" : "confirm.ptype.deal")}
        {" · "}
        {t("rating.confirmedOn", { date: formatDate(partnership.confirmed_at) })}
      </div>

      <form onSubmit={onSubmit}>
        <label>{t("confirm.rate.verdictLabel")} *</label>
        <div className="vertical-chips vertical-chips--accent">
          <button
            type="button"
            className={`vertical-chip${verdict === "success" ? " is-selected" : ""}`}
            onClick={() => setVerdict("success")}
          >
            <IconCheck /> {t("rating.verdict.success")}
          </button>
          <button
            type="button"
            className={`vertical-chip${verdict === "nuance" ? " is-selected" : ""}`}
            onClick={() => setVerdict("nuance")}
          >
            <IconWarning /> {t("confirm.rate.verdictBtn.nuance")}
          </button>
          <button
            type="button"
            className={`vertical-chip${verdict === "problematic" ? " is-selected" : ""}`}
            onClick={() => setVerdict("problematic")}
          >
            <IconCross /> {t("confirm.rate.verdictBtn.problematic")}
          </button>
        </div>
        <p className="partner-meta">{t("confirm.rate.commentRule")}</p>

        <label>{t("confirm.rate.commentLabel")}</label>
        <textarea
          rows={3}
          placeholder={t("confirm.rate.commentPlaceholder")}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />

        <div className="hint-block" style={{ marginTop: 12 }}>
          <IconLock /> {t("confirm.rate.footerNote")}
        </div>

        <button className="btn" type="submit" disabled={state.loading || !verdict}>
          {state.loading ? t("confirm.rate.submitting") : t("confirm.rate.submitBtn")}
        </button>
      </form>
      <Msg type="error">{errorText}</Msg>
    </div>
  );
}
