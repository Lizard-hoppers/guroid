import { useEffect, useMemo, useState } from "react";
import {
  getMe, getPositions, getVacancies, getMyVacancies, getVacancy, createVacancy, editVacancy,
  pauseVacancy, resumeVacancy, extendVacancy, closeVacancy, respondVacancy,
  getVacancyResponses, updateResponseStatus, ApiError,
} from "../api.js";
import { Msg, Spinner } from "./Shared.jsx";
import { useLang } from "../i18n.jsx";
import { haptic } from "../telegram.js";

// Те же канонические вертикали, что в SearchScreen.jsx (constants.VERTICALS
// в боте) — намеренно не вынесены в общий модуль ради одного переиспользования.
const VERTICALS = ["Gambling", "Betting", "Crypto", "Dating", "E-Commerce", "FinTech", "Nutra", "Other"];
const WORK_FORMATS = ["remote", "office", "hybrid"];
const EMPLOYMENT_TYPES = ["full", "part", "project"];
const DURATIONS = [15, 30, 60];
const RESPONSE_STATUSES = ["new", "reviewing", "interview", "offer", "hired", "rejected"];

// Справочник должностей (Приложение к ТЗ "Recruitment — ВАКАНСИИ") — уже
// есть готовый на бэкенде (professions_data.py, 1:1 совпадает с приложением),
// грузим один раз через /api/positions, а не переносим руками.
function usePositions() {
  const [state, setState] = useState({ loading: true, grades: [], professions: {} });
  useEffect(() => {
    let cancelled = false;
    getPositions()
      .then((d) => !cancelled && setState({ loading: false, grades: d.grades, professions: d.professions }))
      .catch(() => !cancelled && setState({ loading: false, grades: [], professions: {} }));
    return () => {
      cancelled = true;
    };
  }, []);
  return state;
}

function flattenPositions(professions) {
  const out = [];
  for (const vertical of Object.keys(professions)) {
    for (const grade of Object.keys(professions[vertical])) {
      for (const [, label] of professions[vertical][grade]) {
        out.push({ vertical, grade, label });
      }
    }
  }
  return out;
}

function StatusBadge({ status }) {
  const { t } = useLang();
  const cls = status === "active" ? "vacancy-status-active" : status === "paused" ? "vacancy-status-paused" : "vacancy-status-closed";
  return <span className={`vacancy-status-badge ${cls}`}>{t(`vacancies.status.${status}`)}</span>;
}

function daysAgo(createdAt) {
  if (!createdAt) return null;
  const then = new Date(createdAt.replace(" ", "T") + "Z").getTime();
  if (Number.isNaN(then)) return null;
  const diffDays = Math.max(0, Math.floor((Date.now() - then) / 86400000));
  return diffDays;
}

// Вертикаль -> Грейд -> Должность (+ "Другое" свободным текстом, раздел 3
// п.4 ТЗ) — переиспользуется и в форме публикации, и в фильтре доски.
function PositionCascadeSelect({ positions, vertical, grade, position, positionIsOther, onChange }) {
  const { t } = useLang();
  const gradeOptions = positions.grades;
  const positionOptions = vertical && grade ? (positions.professions[vertical]?.[grade] || []) : [];

  return (
    <>
      <label>{t("vacancies.form.verticalLabel")}</label>
      <select value={vertical} onChange={(e) => onChange({ vertical: e.target.value, grade: "", position: "", positionIsOther: false })}>
        <option value="">{t("vacancies.allVerticals")}</option>
        {VERTICALS.map((v) => (
          <option key={v} value={v}>{v}</option>
        ))}
      </select>

      <label>{t("vacancies.form.gradeLabel")}</label>
      <select
        value={grade}
        disabled={!vertical}
        onChange={(e) => onChange({ vertical, grade: e.target.value, position: "", positionIsOther: false })}
      >
        <option value="">{t("vacancies.form.gradePlaceholder")}</option>
        {gradeOptions.map((g) => (
          <option key={g} value={g}>{g}</option>
        ))}
      </select>

      <label>{t("vacancies.form.positionLabel")}</label>
      <select
        value={positionIsOther ? "__other__" : position}
        disabled={!vertical || !grade}
        onChange={(e) => {
          if (e.target.value === "__other__") {
            onChange({ vertical, grade, position: "", positionIsOther: true });
          } else {
            onChange({ vertical, grade, position: e.target.value, positionIsOther: false });
          }
        }}
      >
        <option value="">{t("vacancies.form.positionPlaceholder")}</option>
        {positionOptions.map(([code, label]) => (
          <option key={code} value={label}>{label}</option>
        ))}
        <option value="__other__">{t("vacancies.form.positionOther")}</option>
      </select>

      {positionIsOther && (
        <input
          type="text"
          placeholder={t("vacancies.form.positionOtherPlaceholder")}
          value={position}
          onChange={(e) => onChange({ vertical, grade, position: e.target.value, positionIsOther: true })}
        />
      )}
    </>
  );
}

const EMPTY_FORM = {
  title: "", vertical: "", grade: "", position: "", positionIsOther: false, location: "",
  workFormat: "", employmentType: "", salaryFrom: "", salaryTo: "", salaryNegotiable: false,
  salaryVisible: false, description: "", contactMethod: "guro_id", contactUrl: "",
  durationDays: 30, lang: "ru",
};

function vacancyToForm(v) {
  return {
    title: v.title || "", vertical: v.vertical || "", grade: v.grade || "",
    position: v.position || "", positionIsOther: !!v.position_is_other, location: v.location || "",
    workFormat: v.work_format || "", employmentType: v.employment_type || "",
    salaryFrom: v.salary_from ?? "", salaryTo: v.salary_to ?? "", salaryNegotiable: !!v.salary_negotiable,
    salaryVisible: !!v.salary_visible, description: v.description || "",
    contactMethod: v.contact_method || "guro_id", contactUrl: v.contact_url || "",
    durationDays: v.duration_days || 30, lang: v.lang || "ru",
  };
}

// Форма публикации/редактирования (раздел 3 ТЗ, 13 полей) — один компонент
// на оба случая: editingId=null -> POST /api/vacancies, иначе -> POST
// /api/vacancies/{id}/edit (тогда duration_days/lang скрыты — продление
// и повторная публикация на другом языке отдельные действия).
function VacancyForm({ editingId, initial, authorWorkspace, canRecruiter, canCompany, onSaved, onCancel }) {
  const { t } = useLang();
  const positions = usePositions();
  const flat = useMemo(() => flattenPositions(positions.professions), [positions.professions]);
  const [form, setForm] = useState(initial || EMPTY_FORM);
  const [workspace, setWorkspace] = useState(authorWorkspace || (canRecruiter ? "recruiter" : "company"));
  const [suggestions, setSuggestions] = useState([]);
  const [lastPicked, setLastPicked] = useState(initial?.position || "");
  const [state, setState] = useState({ loading: false, error: null });

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  function onTitleChange(value) {
    set("title", value);
    if (value.trim().length >= 3) {
      const q = value.trim().toLowerCase();
      setSuggestions(flat.filter((p) => p.label.toLowerCase().includes(q)).slice(0, 6));
    } else {
      setSuggestions([]);
    }
  }

  function pickSuggestion(s) {
    setForm((f) => ({
      ...f, title: s.label, vertical: s.vertical, grade: s.grade, position: s.label, positionIsOther: false,
    }));
    setLastPicked(s.label);
    setSuggestions([]);
  }

  const mismatch = lastPicked && form.title && !form.title.toLowerCase().includes(lastPicked.toLowerCase());

  async function onSubmit(e) {
    e.preventDefault();
    if (!form.title.trim()) {
      setState({ loading: false, error: t("vacancies.form.titleRequired") });
      return;
    }
    setState({ loading: true, error: null });
    const payload = {
      title: form.title.trim(),
      vertical: form.vertical || null,
      grade: form.grade || null,
      position: form.position || null,
      position_is_other: form.positionIsOther,
      location: form.location || null,
      work_format: form.workFormat || null,
      employment_type: form.employmentType || null,
      salary_from: form.salaryNegotiable ? null : form.salaryFrom || null,
      salary_to: form.salaryNegotiable ? null : form.salaryTo || null,
      salary_negotiable: form.salaryNegotiable,
      salary_visible: form.salaryVisible,
      description: form.description || null,
      contact_method: form.contactMethod,
      contact_url: form.contactMethod === "external" ? form.contactUrl || null : null,
      lang: form.lang,
    };
    try {
      if (editingId) {
        const v = await editVacancy(editingId, payload);
        haptic("success");
        onSaved(v);
      } else {
        const v = await createVacancy({ ...payload, author_workspace: workspace, duration_days: form.durationDays });
        haptic("success");
        onSaved(v);
      }
    } catch (error) {
      setState({
        loading: false,
        error: error instanceof ApiError && error.code === "COMPANY_SUBSCRIPTION_REQUIRED"
          ? t("vacancies.form.companySubRequired")
          : error instanceof ApiError && error.code === "RECRUITER_SUBSCRIPTION_REQUIRED"
            ? t("vacancies.form.recruiterSubRequired")
            : t("vacancies.form.error"),
      });
      haptic("error");
    }
  }

  return (
    <div className="card">
      <h3>{editingId ? t("vacancies.form.editTitle") : t("vacancies.form.title")}</h3>

      {!editingId && canRecruiter && canCompany && (
        <>
          <label>{t("vacancies.form.authorWorkspaceLabel")}</label>
          <div className="vertical-chips">
            <button
              type="button"
              className={`vertical-chip${workspace === "recruiter" ? " is-selected" : ""}`}
              onClick={() => setWorkspace("recruiter")}
            >
              {t("workspace.recruiter")}
            </button>
            <button
              type="button"
              className={`vertical-chip${workspace === "company" ? " is-selected" : ""}`}
              onClick={() => setWorkspace("company")}
            >
              {t("workspace.company")}
            </button>
          </div>
        </>
      )}

      <form onSubmit={onSubmit}>
        <label>{t("vacancies.form.titleLabel")}</label>
        <input
          type="text"
          placeholder={t("vacancies.form.titlePlaceholder")}
          value={form.title}
          onChange={(e) => onTitleChange(e.target.value)}
        />
        {suggestions.length > 0 && (
          <div className="title-suggestions">
            {suggestions.map((s, i) => (
              <button type="button" key={i} className="title-suggestion" onClick={() => pickSuggestion(s)}>
                {s.label} <span className="partner-meta">— {s.vertical} · {s.grade}</span>
              </button>
            ))}
          </div>
        )}
        {mismatch && <div className="mismatch-banner">{t("vacancies.form.mismatchWarning")}</div>}

        <PositionCascadeSelect
          positions={positions}
          vertical={form.vertical}
          grade={form.grade}
          position={form.position}
          positionIsOther={form.positionIsOther}
          onChange={({ vertical, grade, position, positionIsOther }) =>
            setForm((f) => ({ ...f, vertical, grade, position, positionIsOther }))
          }
        />

        <label>{t("vacancies.form.locationLabel")}</label>
        <input
          type="text"
          placeholder={t("vacancies.form.locationPlaceholder")}
          value={form.location}
          onChange={(e) => set("location", e.target.value)}
        />

        <label>{t("vacancies.form.workFormatLabel")}</label>
        <div className="vertical-chips">
          {WORK_FORMATS.map((wf) => (
            <button
              key={wf}
              type="button"
              className={`vertical-chip${form.workFormat === wf ? " is-selected" : ""}`}
              onClick={() => set("workFormat", form.workFormat === wf ? "" : wf)}
            >
              {t(`vacancies.workFormat.${wf}`)}
            </button>
          ))}
        </div>

        <label>{t("vacancies.form.employmentLabel")}</label>
        <div className="vertical-chips">
          {EMPLOYMENT_TYPES.map((et) => (
            <button
              key={et}
              type="button"
              className={`vertical-chip${form.employmentType === et ? " is-selected" : ""}`}
              onClick={() => set("employmentType", form.employmentType === et ? "" : et)}
            >
              {t(`vacancies.employment.${et}`)}
            </button>
          ))}
        </div>

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
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.salaryVisible}
            onChange={(e) => set("salaryVisible", e.target.checked)}
            disabled={form.salaryNegotiable}
          />
          {t("vacancies.form.salaryVisibleLabel")}
        </label>

        <label>{t("vacancies.form.descriptionLabel")}</label>
        <textarea
          rows={4}
          placeholder={t("vacancies.form.descriptionPlaceholder")}
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
        />

        <label>{t("vacancies.form.contactMethodLabel")}</label>
        <div className="vertical-chips">
          <button
            type="button"
            className={`vertical-chip${form.contactMethod === "guro_id" ? " is-selected" : ""}`}
            onClick={() => set("contactMethod", "guro_id")}
          >
            {t("vacancies.form.contactGuroId")}
          </button>
          <button
            type="button"
            className={`vertical-chip${form.contactMethod === "external" ? " is-selected" : ""}`}
            onClick={() => set("contactMethod", "external")}
          >
            {t("vacancies.form.contactExternal")}
          </button>
        </div>
        {form.contactMethod === "external" && (
          <input
            type="text"
            placeholder={t("vacancies.form.contactUrlPlaceholder")}
            value={form.contactUrl}
            onChange={(e) => set("contactUrl", e.target.value)}
          />
        )}

        {!editingId && (
          <>
            <label>{t("vacancies.form.durationLabel")}</label>
            <div className="vertical-chips">
              {DURATIONS.map((d) => (
                <button
                  key={d}
                  type="button"
                  className={`vertical-chip${form.durationDays === d ? " is-selected" : ""}`}
                  onClick={() => set("durationDays", d)}
                >
                  {t("vacancies.form.durationDays", { days: d })}
                </button>
              ))}
            </div>

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
          </>
        )}

        <button className="btn" type="submit" disabled={state.loading} style={{ marginTop: 14 }}>
          {state.loading
            ? t("vacancies.form.submitting")
            : editingId
              ? t("vacancies.form.saveBtn")
              : t("vacancies.form.submit")}
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

// Компактная карточка доски (раздел 2 ТЗ) — без описания, тап открывает
// полную карточку.
function VacancyCard({ v, onOpen }) {
  const { t } = useLang();
  const salaryText = v.salary_negotiable
    ? t("vacancies.salaryNegotiable")
    : v.salary_from != null || v.salary_to != null
      ? `$${v.salary_from ?? "?"} – $${v.salary_to ?? "?"}`
      : null;
  const days = daysAgo(v.created_at);
  return (
    <div className="card vacancy-card" onClick={() => onOpen(v.id)} role="button" tabIndex={0}>
      <h3>{v.title}</h3>
      <div className="partner-meta">
        {[v.vertical, v.grade].filter(Boolean).join(" · ")}
      </div>
      <div className="partner-meta">
        {[v.location, v.work_format && t(`vacancies.workFormat.${v.work_format}`)].filter(Boolean).join(" · ")}
      </div>
      {salaryText && <div className="partner-meta" style={{ marginTop: 4 }}>{salaryText}</div>}
      <div className="partner-meta" style={{ marginTop: 6 }}>
        {[v.company || v.poster_name, v.verified_company && t("vacancies.verifiedCompany")].filter(Boolean).join(" · ")}
      </div>
      {days != null && (
        <div className="partner-meta" style={{ marginTop: 4 }}>
          {days === 0 ? t("vacancies.postedToday") : t("vacancies.postedAgo", { days })}
        </div>
      )}
    </div>
  );
}

// Полная карточка (раздел 2.1 ТЗ) — описание скрыто за кнопкой, кнопки
// действий разные для владельца и для остальных.
function VacancyDetail({ id, onBack, onOpenMessages, onManage, onOpenResponses }) {
  const { t } = useLang();
  const [state, setState] = useState({ loading: true, v: null, error: null });
  const [descOpen, setDescOpen] = useState(false);
  const [respondState, setRespondState] = useState({ loading: false, ok: false, error: null });

  function load() {
    setState({ loading: true, v: null, error: null });
    getVacancy(id)
      .then((v) => setState({ loading: false, v, error: null }))
      .catch((error) => setState({ loading: false, v: null, error }));
  }

  useEffect(load, [id]);

  async function onRespond() {
    setRespondState({ loading: true, ok: false, error: null });
    try {
      await respondVacancy(id, null);
      setRespondState({ loading: false, ok: true, error: null });
      haptic("success");
    } catch (error) {
      setRespondState({
        loading: false, ok: false,
        error: error instanceof ApiError && error.code === "ALREADY_RESPONDED"
          ? t("vacancies.respondError.ALREADY_RESPONDED")
          : t("vacancies.respondError.generic"),
      });
      haptic("error");
    }
  }

  if (state.loading) return <Spinner>{t("messages.loading")}</Spinner>;
  if (!state.v) return <Msg type="error">{t("vacancies.loadError")}</Msg>;

  const v = state.v;
  const salaryText = v.salary_negotiable
    ? t("vacancies.salaryNegotiable")
    : v.salary_from != null || v.salary_to != null
      ? `$${v.salary_from ?? "?"} – $${v.salary_to ?? "?"}`
      : null;

  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <div className="card">
        <StatusBadge status={v.status} />
        <h2 style={{ marginTop: 8 }}>{v.title}</h2>
        <div className="partner-meta">{[v.vertical, v.grade, v.position].filter(Boolean).join(" · ")}</div>
        <div className="partner-meta">
          {[v.location, v.work_format && t(`vacancies.workFormat.${v.work_format}`), v.employment_type && t(`vacancies.employment.${v.employment_type}`)]
            .filter(Boolean).join(" · ")}
        </div>
        {salaryText && <div className="partner-meta" style={{ marginTop: 6 }}>{salaryText}</div>}
        <div className="partner-meta" style={{ marginTop: 8 }}>
          {[v.company || v.poster_name, v.verified_company && t("vacancies.verifiedCompany")].filter(Boolean).join(" · ")}
          {typeof v.reputation_score === "number" && ` · ★ ${v.reputation_score}`}
        </div>

        {v.description && !descOpen && (
          <button type="button" className="btn secondary" style={{ marginTop: 12 }} onClick={() => setDescOpen(true)}>
            {t("vacancies.showDescription")}
          </button>
        )}
        {v.description && descOpen && (
          <div className="partner-meta" style={{ marginTop: 10, whiteSpace: "pre-wrap" }}>{v.description}</div>
        )}

        {v.is_owner ? (
          <>
            <div className="partner-meta" style={{ marginTop: 12 }}>
              {t("vacancies.viewsLabel", { n: v.views_count })} · {t("vacancies.responsesLabel", { n: v.responses_count })}
            </div>
            <div className="recruiter-quick-actions" style={{ marginTop: 12 }}>
              <button type="button" className="btn secondary" onClick={() => onManage("edit", v)}>
                {t("vacancies.manage.edit")}
              </button>
              <button type="button" className="btn secondary" onClick={() => onOpenResponses(v.id)}>
                {t("vacancies.responses.title")} ({v.responses_count})
              </button>
            </div>
            <div className="recruiter-quick-actions" style={{ marginTop: 8 }}>
              {v.status === "active" && (
                <button type="button" className="btn secondary" onClick={() => onManage("pause", v)}>
                  {t("vacancies.manage.pause")}
                </button>
              )}
              {v.status === "paused" && (
                <button type="button" className="btn secondary" onClick={() => onManage("resume", v)}>
                  {t("vacancies.manage.resume")}
                </button>
              )}
              {v.status !== "closed" && (
                <button type="button" className="btn secondary" onClick={() => onManage("extend", v)}>
                  {t("vacancies.manage.extend")}
                </button>
              )}
              {v.status !== "closed" && (
                <button type="button" className="btn secondary" onClick={() => onManage("close", v)}>
                  {t("vacancies.manage.close")}
                </button>
              )}
            </div>
          </>
        ) : (
          <>
            <button type="button" className="btn secondary" style={{ marginTop: 12 }} onClick={() => onOpenMessages(v.author_id)}>
              {t("vacancies.writeBtn")}
            </button>
            {v.contact_method === "external" ? (
              v.contact_url && (
                <a className="btn" style={{ marginTop: 8, display: "block", textAlign: "center", textDecoration: "none" }} href={v.contact_url} target="_blank" rel="noreferrer">
                  {t("vacancies.externalApplyBtn")}
                </a>
              )
            ) : (
              <button type="button" className="btn" style={{ marginTop: 8 }} onClick={onRespond} disabled={respondState.loading || respondState.ok}>
                {respondState.ok ? t("vacancies.respondSentOk") : t("vacancies.applyBtn")}
              </button>
            )}
            <Msg type="error">{respondState.error}</Msg>
          </>
        )}
      </div>
    </div>
  );
}

// "Мои вакансии" (раздел 4 ТЗ) — статус/счётчики/действия, тап по строке
// открывает полную карточку (там же кнопки управления).
function MyVacancies({ onOpen, onManage, refreshKey }) {
  const { t } = useLang();
  const [state, setState] = useState({ loading: true, vacancies: null, error: null });

  function load() {
    setState({ loading: true, vacancies: null, error: null });
    getMyVacancies()
      .then(({ vacancies }) => setState({ loading: false, vacancies, error: null }))
      .catch((error) => setState({ loading: false, vacancies: null, error }));
  }

  useEffect(load, [refreshKey]);

  if (state.loading) return <Spinner>{t("messages.loading")}</Spinner>;
  if (state.error) return <Msg type="error">{t("vacancies.loadError")}</Msg>;
  if (!state.vacancies || state.vacancies.length === 0) {
    return <div className="partner-meta">{t("vacancies.mineEmpty")}</div>;
  }

  function act(e, action, v) {
    e.stopPropagation();
    onManage(action, v, { stay: true });
  }

  return (
    <div>
      {state.vacancies.map((v) => (
        <div key={v.id} className="card">
          <div className="partner-row" style={{ alignItems: "center", cursor: "pointer" }} onClick={() => onOpen(v.id)}>
            <div className="partner-info">
              <div className="partner-name">{v.title}</div>
              <div className="partner-meta">{[v.vertical, v.grade].filter(Boolean).join(" · ")}</div>
              <div className="partner-meta">
                {t("vacancies.viewsLabel", { n: v.views_count })} · {t("vacancies.responsesLabel", { n: v.responses_count })}
              </div>
            </div>
            <StatusBadge status={v.status} />
          </div>
          <div className="recruiter-quick-actions" style={{ marginTop: 10, flexWrap: "wrap" }}>
            <button type="button" className="btn secondary" onClick={(e) => act(e, "edit", v)}>
              {t("vacancies.manage.edit")}
            </button>
            {v.status === "active" && (
              <button type="button" className="btn secondary" onClick={(e) => act(e, "pause", v)}>
                {t("vacancies.manage.pause")}
              </button>
            )}
            {v.status === "paused" && (
              <button type="button" className="btn secondary" onClick={(e) => act(e, "resume", v)}>
                {t("vacancies.manage.resume")}
              </button>
            )}
            {v.status !== "closed" && (
              <button type="button" className="btn secondary" onClick={(e) => act(e, "extend", v)}>
                {t("vacancies.manage.extend")}
              </button>
            )}
            {v.status !== "closed" && (
              <button type="button" className="btn secondary" onClick={(e) => act(e, "close", v)}>
                {t("vacancies.manage.close")}
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

const RESPONSE_ERROR_KEYS = {
  NOT_FOUND: "vacancies.responses.errorGeneric",
  INVALID_STATUS: "vacancies.responses.errorGeneric",
};

// Отклики по одной вакансии (раздел 5.2-5.4 ТЗ) — мини-ATS: воронка
// статусов + карточка отклика с "Подтвердить найм" (префилл формы найма
// кабинета Рекрутер, см. ConfirmScreen.jsx/App.jsx::openHireConfirm).
function VacancyResponses({ vacancyId, onBack, onOpenMessages, onOpenHireConfirm }) {
  const { t } = useLang();
  const [statusFilter, setStatusFilter] = useState("");
  const [state, setState] = useState({ loading: true, vacancy: null, responses: null, error: null });

  function load() {
    setState((s) => ({ ...s, loading: true, error: null }));
    getVacancyResponses(vacancyId, { status: statusFilter || undefined })
      .then(({ vacancy, responses }) => setState({ loading: false, vacancy, responses, error: null }))
      .catch((error) => setState({ loading: false, vacancy: null, responses: null, error }));
  }

  useEffect(load, [vacancyId, statusFilter]);

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
    const parts = [state.vacancy?.title, state.vacancy?.vertical, state.vacancy?.grade, state.vacancy?.position].filter(Boolean);
    onOpenHireConfirm({
      confirmerUsername: r.candidate_username || "",
      vertical: state.vacancy?.vertical || "",
      offer: parts.join(" · "),
    });
  }

  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <div className="card">
        <h3>{t("vacancies.responses.title")}</h3>
        {state.vacancy && <div className="partner-meta">{state.vacancy.title}</div>}
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
      {state.error && <Msg type="error">{t("vacancies.loadError")}</Msg>}
      {state.responses && state.responses.length === 0 && (
        <div className="partner-meta">{t("vacancies.responses.empty")}</div>
      )}
      {state.responses?.map((r) => (
        <div key={r.id} className="card">
          <div className="partner-name">
            {r.candidate_name || (r.candidate_username ? `@${r.candidate_username}` : t("common.noName"))}
          </div>
          <div className="partner-meta">
            {[r.candidate_vertical, typeof r.reputation_score === "number" ? `★ ${r.reputation_score}` : null].filter(Boolean).join(" · ")}
          </div>
          {r.message && <div className="partner-meta" style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{r.message}</div>}
          <select value={r.status} onChange={(e) => setStatus(r.id, e.target.value)} style={{ marginTop: 10 }}>
            {RESPONSE_STATUSES.map((s) => (
              <option key={s} value={s}>{t(`vacancies.responses.status.${s}`)}</option>
            ))}
          </select>
          <div className="recruiter-quick-actions" style={{ marginTop: 10 }}>
            {r.candidate_username && (
              <button type="button" className="btn secondary" onClick={() => onOpenMessages(r.candidate_id)}>
                {t("vacancies.writeBtn")}
              </button>
            )}
            <button type="button" className="btn" onClick={() => confirmHire(r)}>
              {t("vacancies.responses.confirmHireBtn")}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

export function VacanciesScreen({ onNavigate, onOpenMessages, onOpenHireConfirm }) {
  const { t, lang } = useLang();
  const positions = usePositions();
  const [tab, setTab] = useState("board"); // "board" | "mine"
  const [view, setView] = useState({ name: "board" });
  const [caps, setCaps] = useState({ loading: true, recruiter: false, company: false });
  const [refreshKey, setRefreshKey] = useState(0);

  const [langFilter, setLangFilter] = useState(lang === "en" ? "en" : "ru");
  const [vertical, setVertical] = useState("");
  const [grade, setGrade] = useState("");
  const [position, setPosition] = useState("");
  const [q, setQ] = useState("");
  const [state, setState] = useState({ loading: true, vacancies: null, truncated: false, error: null });

  useEffect(() => {
    Promise.all([
      getMe({ workspace: "recruiter" }).then((d) => !!d.is_recruiter_subscribed).catch(() => false),
      getMe({ workspace: "company" }).then((d) => !!d.is_company_subscribed).catch(() => false),
    ]).then(([recruiter, company]) => setCaps({ loading: false, recruiter, company }));
  }, []);

  function loadList() {
    setState({ loading: true, vacancies: null, truncated: false, error: null });
    getVacancies({ lang: langFilter, vertical: vertical || undefined, grade: grade || undefined, position: position || undefined, q: q || undefined })
      .then(({ vacancies, truncated }) => setState({ loading: false, vacancies, truncated, error: null }))
      .catch((error) => setState({ loading: false, vacancies: null, truncated: false, error }));
  }

  useEffect(loadList, [langFilter, vertical, grade, position, q, refreshKey]);

  const canPublish = caps.recruiter || caps.company;
  const subscriptionRequired = state.error instanceof ApiError && state.error.status === 402;

  // stay=true (26.08.2026, ТЗ "рекрутер вакансии", Экран 3) — действия
  // прямо со строки "Мои вакансии" не должны уводить на полную карточку,
  // остаёмся в списке (в отличие от тех же действий с экрана детали).
  async function onManage(action, v, { stay } = {}) {
    try {
      if (action === "edit") {
        setView({ name: "edit", id: v.id, initial: vacancyToForm(v) });
        return;
      }
      if (action === "pause") await pauseVacancy(v.id);
      if (action === "resume") await resumeVacancy(v.id);
      if (action === "extend") await extendVacancy(v.id, 30);
      if (action === "close") await closeVacancy(v.id, null);
      haptic("light");
      if (!stay) setView({ name: "detail", id: v.id });
      setRefreshKey((k) => k + 1);
    } catch {
      haptic("error");
    }
  }

  if (view.name === "detail") {
    return (
      <VacancyDetail
        id={view.id}
        onBack={() => {
          setView({ name: "board" });
          setRefreshKey((k) => k + 1);
        }}
        onOpenMessages={onOpenMessages}
        onManage={onManage}
        onOpenResponses={(id) => setView({ name: "responses", id })}
      />
    );
  }

  if (view.name === "responses") {
    return (
      <VacancyResponses
        vacancyId={view.id}
        onBack={() => setView({ name: "detail", id: view.id })}
        onOpenMessages={onOpenMessages}
        onOpenHireConfirm={onOpenHireConfirm}
      />
    );
  }

  if (view.name === "form" || view.name === "edit") {
    return (
      <VacancyForm
        editingId={view.name === "edit" ? view.id : null}
        initial={view.initial}
        canRecruiter={caps.recruiter}
        canCompany={caps.company}
        onSaved={() => {
          setView(view.name === "edit" ? { name: "detail", id: view.id } : { name: "board" });
          setRefreshKey((k) => k + 1);
        }}
        onCancel={() => setView(view.name === "edit" ? { name: "detail", id: view.id } : { name: "board" })}
      />
    );
  }

  return (
    <div>
      <div className="card">
        <h3>{t("vacancies.title")}</h3>
        <div className="partner-meta" style={{ marginBottom: 10 }}>{t("vacancies.hint")}</div>

        <div className="workspace-switch">
          <button type="button" className={tab === "board" ? "is-active" : ""} onClick={() => setTab("board")}>
            {t("vacancies.tabBoard")}
          </button>
          {canPublish && (
            <button type="button" className={tab === "mine" ? "is-active" : ""} onClick={() => setTab("mine")}>
              {t("vacancies.tabMine")}
            </button>
          )}
        </div>

        {tab === "board" && (
          <>
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
                onClick={() => { setVertical(""); setGrade(""); setPosition(""); }}
              >
                {t("vacancies.allVerticals")}
              </button>
              {VERTICALS.map((v) => (
                <button
                  key={v}
                  type="button"
                  className={`vertical-chip${vertical === v ? " is-selected" : ""}`}
                  onClick={() => { setVertical(v); setGrade(""); setPosition(""); }}
                >
                  {v}
                </button>
              ))}
            </div>
            {vertical && (
              <select value={grade} onChange={(e) => { setGrade(e.target.value); setPosition(""); }} style={{ marginTop: 8 }}>
                <option value="">{t("vacancies.form.gradePlaceholder")}</option>
                {positions.grades.map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>
            )}
            <input
              type="text"
              placeholder={t("vacancies.searchPlaceholder")}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ marginTop: 8 }}
            />
          </>
        )}

        {tab === "board" && (
          canPublish ? (
            <button className="btn" style={{ marginTop: 14 }} onClick={() => setView({ name: "form" })}>
              {t("vacancies.publishBtn")}
            </button>
          ) : (
            !caps.loading && <div className="partner-meta" style={{ marginTop: 14 }}>{t("vacancies.upsellText")}</div>
          )
        )}
      </div>

      {tab === "mine" && (
        <MyVacancies onOpen={(id) => setView({ name: "detail", id })} onManage={onManage} refreshKey={refreshKey} />
      )}

      {tab === "board" && (
        <>
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
            <VacancyCard key={v.id} v={v} onOpen={(id) => setView({ name: "detail", id })} />
          ))}
          {state.truncated && <div className="partner-meta">{t("vacancies.truncatedHint")}</div>}
        </>
      )}
    </div>
  );
}
