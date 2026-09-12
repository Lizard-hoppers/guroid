import { useEffect, useState } from "react";
import { getMyResponses, updateResponseStatus } from "../../api.js";
import { Msg, Spinner } from "../Shared.jsx";
import { ResponseStatusDot, ResponseMark } from "../VacanciesScreen.jsx";
import { useLang } from "../../i18n.jsx";
import { haptic } from "../../telegram.js";

const RESPONSE_STATUSES = ["new", "reviewing", "interview", "offer", "hired", "rejected"];

// "Отклики" (ТЗ "Гуро рекрутер каб", раздел 2.7 + ТЗ "Recruitment —
// ВАКАНСИИ", раздел 5.5) — агрегация по ВСЕМ своим вакансиям (не по одной),
// каждая строка подписана названием вакансии. Раньше была честной
// заглушкой (механика откликов ещё не существовала) — теперь реальные
// данные через GET /api/responses.
export function RecruiterResponsesSubscreen({ onBack, onWrite, onConfirmHire }) {
  const { t } = useLang();
  const [statusFilter, setStatusFilter] = useState("");
  const [state, setState] = useState({ loading: true, responses: null, error: null });

  function load() {
    setState((s) => ({ ...s, loading: true, error: null }));
    getMyResponses({ status: statusFilter || undefined })
      .then(({ responses }) => setState({ loading: false, responses, error: null }))
      .catch((error) => setState({ loading: false, responses: null, error }));
  }

  useEffect(load, [statusFilter]);

  async function setStatus(responseId, status) {
    try {
      await updateResponseStatus(responseId, status);
      haptic("light");
      load();
    } catch {
      haptic("error");
    }
  }

  function confirmHire(r) {
    onConfirmHire({
      confirmerUsername: r.candidate_username || "",
      vertical: r.candidate_vertical || "",
      offer: r.vacancy_title || "",
    });
  }

  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <div className="card">
        <h3>{t("recruiter.responses.title")}</h3>
        <div className="vertical-chips" style={{ marginTop: 8 }}>
          <button
            type="button"
            className={`vertical-chip${statusFilter === "" ? " is-selected" : ""}`}
            onClick={() => setStatusFilter("")}
          >
            {t("vacancies.responses.statusAll")}
          </button>
          {RESPONSE_STATUSES.map((s) => (
            <button
              key={s}
              type="button"
              className={`vertical-chip${statusFilter === s ? " is-selected" : ""}`}
              onClick={() => setStatusFilter(s)}
            >
              {t(`vacancies.responses.status.${s}`)}
            </button>
          ))}
        </div>
      </div>

      {state.loading && <Spinner>{t("messages.loading")}</Spinner>}
      {state.error && <Msg type="error">{t("recruiter.responses.loadError")}</Msg>}
      {state.responses && state.responses.length === 0 && (
        <div className="partner-meta">{t("recruiter.responses.empty")}</div>
      )}
      {state.responses?.map((r) => {
        const days = daysAgo(r.created_at);
        return (
          <div key={r.id} className="card">
            <div className="vacancy-response-head">
              <div className="partner-name">{r.vacancy_title}</div>
              {typeof r.reputation_score === "number" && (
                <div className="rating-preview-circle vacancy-response-rating">{Math.round(r.reputation_score)}</div>
              )}
            </div>
            <div className="partner-meta">
              {r.candidate_name || (r.candidate_username ? `@${r.candidate_username}` : t("common.noName"))}
              {r.candidate_vertical ? ` · ${r.candidate_vertical}` : ""}
            </div>
            <div className="vacancy-mine-status-row vacancy-mine-status-row--response" style={{ marginTop: 8 }}>
              <ResponseStatusDot status={r.status} />
              {days !== null && (
                <span className="vacancy-mine-counts">
                  <ResponseMark status={r.status} />{" "}
                  {days === 0 ? t("vacancies.responses.today") : t("vacancies.responses.daysAgo", { days })}
                </span>
              )}
            </div>
            {r.message && <div className="partner-meta" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>{r.message}</div>}
            <select value={r.status} onChange={(e) => setStatus(r.id, e.target.value)} style={{ marginTop: 12 }}>
              {RESPONSE_STATUSES.map((s) => (
                <option key={s} value={s}>{t(`vacancies.responses.status.${s}`)}</option>
              ))}
            </select>
            <div className="recruiter-quick-actions" style={{ marginTop: 12 }}>
              {r.candidate_username && (
                <button type="button" className="btn secondary" onClick={() => onWrite(r.candidate_id)}>
                  {t("vacancies.writeBtn")}
                </button>
              )}
              {r.status === "hired" && (
                <button type="button" className="btn" onClick={() => confirmHire(r)}>
                  {t("vacancies.responses.confirmHireBtn")}
                </button>
              )}
            </div>
          </div>
        );
      })}

      {state.responses && state.responses.length > 0 && (
        <div className="profile-privacy-locked-note vacancy-hire-explainer">
          <div className="profile-privacy-locked-title vacancy-hire-explainer-title">
            {t("vacancies.responses.hireExplainerTitle")}
          </div>
          <div className="privacy-row-note">{t("vacancies.responses.hireExplainerText")}</div>
        </div>
      )}
    </div>
  );
}

function daysAgo(dateStr) {
  if (!dateStr) return null;
  const then = new Date(dateStr.replace(" ", "T") + "Z").getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.floor((Date.now() - then) / 86400000));
}
