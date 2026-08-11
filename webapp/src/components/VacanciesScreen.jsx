import { useEffect, useState } from "react";
import { getMe, getVacancies, getMyVacancies, createVacancy, closeVacancy, ApiError } from "../api.js";
import { Msg, Spinner } from "./Shared.jsx";
import { useLang } from "../i18n.jsx";
import { haptic } from "../telegram.js";

// Те же канонические вертикали, что в SearchScreen.jsx (constants.VERTICALS
// в боте) — намеренно не вынесены в общий модуль ради одного переиспользования.
const VERTICALS = ["Gambling", "Betting", "Crypto", "Dating", "E-Commerce", "FinTech", "Nutra", "Other"];
// Те же грейды, что constants.GRADES в боте (анкета/CV) — свободный текст на
// бэкенде, но фронт предлагает канонический список, а не ручной ввод.
const SENIORITY_LEVELS = ["C-Level", "Head of / Director", "Management", "Senior", "Specialist", "Junior / Entry"];

const EMPTY_FORM = {
  title: "", vertical: "", seniority: "", location: "",
  remote: false, relocation: false,
  salaryFrom: "", salaryTo: "", salaryNegotiable: false,
  description: "", lang: "ru",
};

function VacancyCard({ v, onApply }) {
  const { t } = useLang();
  const salaryText = v.salary_negotiable
    ? t("vacancies.salaryNegotiable")
    : v.salary_from != null || v.salary_to != null
      ? `$${v.salary_from ?? "?"} – $${v.salary_to ?? "?"}`
      : null;
  return (
    <div className="card">
      <h3>{v.title}</h3>
      <div className="partner-meta">
        {[v.company, v.vertical, v.seniority, v.location].filter(Boolean).join(" · ")}
      </div>
      {(v.remote || v.relocation) && (
        <div className="vacancy-badges">
          {v.remote && <span className="badge-unrated">{t("vacancies.remote")}</span>}
          {v.relocation && <span className="badge-unrated">{t("vacancies.relocation")}</span>}
        </div>
      )}
      {salaryText && <div className="partner-meta" style={{ marginTop: 6 }}>{salaryText}</div>}
      {v.description && (
        <div className="partner-meta" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>{v.description}</div>
      )}
      <button type="button" className="btn secondary" style={{ marginTop: 12 }} onClick={() => onApply(v.author_id)}>
        {t("vacancies.applyBtn")}
      </button>
    </div>
  );
}

function VacancyForm({ onCreated, onCancel }) {
  const { t } = useLang();
  const [form, setForm] = useState(EMPTY_FORM);
  const [state, setState] = useState({ loading: false, error: null });

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function onSubmit(e) {
    e.preventDefault();
    if (!form.title.trim()) {
      setState({ loading: false, error: t("vacancies.form.titleRequired") });
      return;
    }
    setState({ loading: true, error: null });
    try {
      await createVacancy({
        title: form.title.trim(),
        vertical: form.vertical || null,
        seniority: form.seniority || null,
        location: form.location || null,
        remote: form.remote,
        relocation: form.relocation,
        salary_from: form.salaryNegotiable ? null : form.salaryFrom || null,
        salary_to: form.salaryNegotiable ? null : form.salaryTo || null,
        salary_negotiable: form.salaryNegotiable,
        description: form.description || null,
        lang: form.lang,
      });
      haptic("success");
      onCreated();
    } catch {
      setState({ loading: false, error: t("vacancies.form.error") });
      haptic("error");
    }
  }

  return (
    <div className="card">
      <h3>{t("vacancies.form.title")}</h3>
      <form onSubmit={onSubmit}>
        <label>{t("vacancies.form.titleLabel")}</label>
        <input
          type="text"
          placeholder={t("vacancies.form.titlePlaceholder")}
          value={form.title}
          onChange={(e) => set("title", e.target.value)}
        />

        <label>{t("vacancies.form.verticalLabel")}</label>
        <div className="vertical-chips">
          {VERTICALS.map((v) => (
            <button
              key={v}
              type="button"
              className={`vertical-chip${form.vertical === v ? " is-selected" : ""}`}
              onClick={() => set("vertical", form.vertical === v ? "" : v)}
            >
              {v}
            </button>
          ))}
        </div>

        <label>{t("vacancies.form.seniorityLabel")}</label>
        <select value={form.seniority} onChange={(e) => set("seniority", e.target.value)}>
          <option value="">{t("vacancies.form.seniorityPlaceholder")}</option>
          {SENIORITY_LEVELS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <label>{t("vacancies.form.locationLabel")}</label>
        <input
          type="text"
          placeholder={t("vacancies.form.locationPlaceholder")}
          value={form.location}
          onChange={(e) => set("location", e.target.value)}
        />

        <label className="checkbox-row">
          <input type="checkbox" checked={form.remote} onChange={(e) => set("remote", e.target.checked)} />
          {t("vacancies.form.remoteLabel")}
        </label>
        <label className="checkbox-row">
          <input type="checkbox" checked={form.relocation} onChange={(e) => set("relocation", e.target.checked)} />
          {t("vacancies.form.relocationLabel")}
        </label>

        <label>{t("vacancies.form.salaryLabel")}</label>
        <div className="amount-row">
          <input
            type="number"
            inputMode="decimal"
            placeholder={t("vacancies.form.salaryFromPlaceholder")}
            value={form.salaryFrom}
            onChange={(e) => set("salaryFrom", e.target.value)}
            disabled={form.salaryNegotiable}
          />
          <input
            type="number"
            inputMode="decimal"
            placeholder={t("vacancies.form.salaryToPlaceholder")}
            value={form.salaryTo}
            onChange={(e) => set("salaryTo", e.target.value)}
            disabled={form.salaryNegotiable}
          />
        </div>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.salaryNegotiable}
            onChange={(e) => set("salaryNegotiable", e.target.checked)}
          />
          {t("vacancies.form.salaryNegotiableLabel")}
        </label>

        <label>{t("vacancies.form.descriptionLabel")}</label>
        <textarea
          rows={4}
          placeholder={t("vacancies.form.descriptionPlaceholder")}
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
        />

        <label>{t("vacancies.form.langLabel")}</label>
        <div className="vertical-chips">
          {["ru", "en"].map((l) => (
            <button
              key={l}
              type="button"
              className={`vertical-chip${form.lang === l ? " is-selected" : ""}`}
              onClick={() => set("lang", l)}
            >
              {l.toUpperCase()}
            </button>
          ))}
        </div>

        <button className="btn" type="submit" disabled={state.loading}>
          {state.loading ? t("vacancies.form.submitting") : t("vacancies.form.submit")}
        </button>
        <button
          className="btn secondary"
          type="button"
          onClick={onCancel}
          disabled={state.loading}
          style={{ marginTop: 8 }}
        >
          {t("common.cancel")}
        </button>
      </form>
      <Msg type="error">{state.error}</Msg>
    </div>
  );
}

export function VacanciesScreen({ onNavigate, onOpenMessages }) {
  const { t, lang } = useLang();
  const [langFilter, setLangFilter] = useState(lang === "en" ? "en" : "ru");
  const [vertical, setVertical] = useState("");
  const [state, setState] = useState({ loading: true, vacancies: null, error: null });
  const [isRecruiter, setIsRecruiter] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [mine, setMine] = useState(null);

  useEffect(() => {
    getMe({ workspace: "recruiter" })
      .then((d) => setIsRecruiter(!!d.is_recruiter_subscribed))
      .catch(() => {});
  }, []);

  function loadList() {
    setState({ loading: true, vacancies: null, error: null });
    getVacancies({ lang: langFilter, vertical: vertical || undefined })
      .then(({ vacancies }) => setState({ loading: false, vacancies, error: null }))
      .catch((error) => setState({ loading: false, vacancies: null, error }));
  }

  useEffect(loadList, [langFilter, vertical]);

  function loadMine() {
    getMyVacancies()
      .then(({ vacancies }) => setMine(vacancies))
      .catch(() => {});
  }

  useEffect(() => {
    if (isRecruiter) loadMine();
  }, [isRecruiter]);

  async function onClose(id) {
    try {
      await closeVacancy(id);
      haptic("light");
      loadMine();
      loadList();
    } catch {
      haptic("error");
    }
  }

  const subscriptionRequired = state.error instanceof ApiError && state.error.status === 402;

  return (
    <div>
      <div className="card">
        <h3>{t("vacancies.title")}</h3>
        <div className="partner-meta" style={{ marginBottom: 10 }}>{t("vacancies.hint")}</div>

        <div className="vertical-chips">
          {["ru", "en"].map((l) => (
            <button
              key={l}
              type="button"
              className={`vertical-chip${langFilter === l ? " is-selected" : ""}`}
              onClick={() => setLangFilter(l)}
            >
              {l.toUpperCase()}
            </button>
          ))}
        </div>
        <div className="vertical-chips" style={{ marginTop: 8 }}>
          <button
            type="button"
            className={`vertical-chip${vertical === "" ? " is-selected" : ""}`}
            onClick={() => setVertical("")}
          >
            {t("vacancies.allVerticals")}
          </button>
          {VERTICALS.map((v) => (
            <button
              key={v}
              type="button"
              className={`vertical-chip${vertical === v ? " is-selected" : ""}`}
              onClick={() => setVertical(v)}
            >
              {v}
            </button>
          ))}
        </div>

        {isRecruiter ? (
          <button className="btn" style={{ marginTop: 14 }} onClick={() => setShowForm((v) => !v)}>
            {t("vacancies.publishBtn")}
          </button>
        ) : (
          <div className="partner-meta" style={{ marginTop: 14 }}>{t("vacancies.upsellText")}</div>
        )}
      </div>

      {showForm && (
        <VacancyForm
          onCreated={() => {
            setShowForm(false);
            loadMine();
            loadList();
          }}
          onCancel={() => setShowForm(false)}
        />
      )}

      {isRecruiter && mine && mine.length > 0 && (
        <div className="card">
          <h3>{t("vacancies.mineTitle")}</h3>
          {mine.map((v) => (
            <div key={v.id} className="partner-row" style={{ alignItems: "center" }}>
              <div className="partner-info">
                <div className="partner-name">
                  {v.title}
                  {v.status === "closed" ? ` · ${t("vacancies.statusClosed")}` : ""}
                </div>
                <div className="partner-meta">{[v.vertical, v.seniority].filter(Boolean).join(" · ")}</div>
              </div>
              {v.status !== "closed" && (
                <button
                  type="button"
                  className="btn secondary"
                  style={{ width: "auto", padding: "8px 14px" }}
                  onClick={() => onClose(v.id)}
                >
                  {t("vacancies.closeBtn")}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {state.loading && <Spinner>{t("messages.loading")}</Spinner>}

      {subscriptionRequired && (
        <div className="directory-paywall">
          <strong>{t("search.paywallTitle")}</strong>
          <button
            className="btn"
            style={{ width: "auto", padding: "10px 20px" }}
            onClick={() => onNavigate("subscribe")}
          >
            {t("rating.subscribeCta")}
          </button>
        </div>
      )}

      {state.error && !subscriptionRequired && <Msg type="error">{t("vacancies.loadError")}</Msg>}

      {state.vacancies && state.vacancies.length === 0 && (
        <div className="partner-meta">{t("vacancies.empty")}</div>
      )}

      {state.vacancies?.map((v) => (
        <VacancyCard key={v.id} v={v} onApply={onOpenMessages} />
      ))}
    </div>
  );
}
