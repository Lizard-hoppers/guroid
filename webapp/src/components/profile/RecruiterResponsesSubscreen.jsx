import { useEffect, useState } from "react";
import { getMyResponses, updateResponseStatus } from "../../api.js";
import { Msg, Spinner } from "../Shared.jsx";
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
      {state.responses?.map((r) => (
        <div key={r.id} className="card">
          <div className="partner-name">{r.vacancy_title}</div>
          <div className="partner-meta">
            {r.candidate_name || (r.candidate_username ? `@${r.candidate_username}` : t("common.noName"))}
            {r.candidate_vertical ? ` · ${r.candidate_vertical}` : ""}
            {/* Звезда снята: она выдавала рабочий рейтинг (шкала 0-100) за оценку
                  из пяти — та же путаница, о которой владелец писал про «★ 1.7». */}
              {typeof r.reputation_score === "number"
                ? ` · ${t("vacancies.posterRating", { n: Math.round(r.reputation_score) })}`
                : ""}
          </div>
          {r.message && <div className="partner-meta" style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{r.message}</div>}
          <select value={r.status} onChange={(e) => setStatus(r.id, e.target.value)} style={{ marginTop: 10 }}>
            {RESPONSE_STATUSES.map((s) => (
              <option key={s} value={s}>{t(`vacancies.responses.status.${s}`)}</option>
            ))}
          </select>
          <div className="recruiter-quick-actions" style={{ marginTop: 10 }}>
            {r.candidate_username && (
              <button type="button" className="btn secondary" onClick={() => onWrite(r.candidate_id)}>
                {t("vacancies.writeBtn")}
              </button>
            )}
            {/* 29.08.2026, регресс — тот же баг чинили в VacancyResponses/
                AllResponses (VacanciesScreen.jsx, макет "16 · Рекрутер —
                Отклики"): кнопка была видна для ЛЮБОГО статуса отклика, не
                только "hired". Это третья, отдельная копия того же экрана
                (доступна из меню кабинета Рекрутера) — фикс сюда не долетел. */}
            {r.status === "hired" && (
              <button type="button" className="btn" onClick={() => confirmHire(r)}>
                {t("vacancies.responses.confirmHireBtn")}
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
