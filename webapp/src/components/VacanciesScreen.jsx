import { useEffect, useMemo, useState } from "react";
import {
  getMe, getPositions, getVacancies, getMyVacancies, getVacancy, createVacancy, editVacancy,
  pauseVacancy, resumeVacancy, extendVacancy, closeVacancy, respondVacancy,
  getVacancyResponses, getMyResponses, updateResponseStatus, ApiError,
} from "../api.js";
import { Msg, Spinner, WorkspaceCabinetBadge } from "./Shared.jsx";
import { useLang } from "../i18n.jsx";
import { haptic } from "../telegram.js";
import { formatDate, initialOf } from "../utils.js";

// Те же канонические вертикали, что в SearchScreen.jsx (constants.VERTICALS
// в боте) — намеренно не вынесены в общий модуль ради одного переиспользования.
const VERTICALS = ["Gambling", "Betting", "Crypto", "Dating", "E-Commerce", "FinTech", "Nutra", "Other"];
const WORK_FORMATS = ["remote", "office", "hybrid"];
const EMPLOYMENT_TYPES = ["full", "part", "project"];
const DURATIONS = [15, 30, 60];
const RESPONSE_STATUSES = ["new", "reviewing", "interview", "offer", "hired", "rejected"];
// "Тип компании" (26.08.2026, ТЗ "Компания. каб", раздел 5) — фильтр доски
// по тегу автора-компании, тот же справочник, что в CompanyHub.jsx/GC.COMPANY_TYPES.
const COMPANY_TYPES = [
  "operator_casino", "bookmaker", "cpa_network", "hr_agency",
  "media_buying", "b2b_platform", "investor_fund",
];

// Справочник должностей (Приложение к ТЗ "Recruitment — ВАКАНСИИ") — уже
// есть готовый на бэкенде (professions_data.py, 1:1 совпадает с приложением),
// грузим один раз через /api/positions, а не переносим руками.
export function usePositions() {
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

// Умное предупреждение о несовпадении (28.08.2026, макет "14 · Рекрутер —
// Опубликовать вакансию") — ищет в СВОБОДНОМ названии позиции слово
// (кроме коротких предлогов/союзов "of"/"and" и т.п. — фильтр по длине)
// из ЛЮБОГО грейда СПРАВОЧНИКА, кроме того, что выбран чипом сейчас.
// Например, название "Senior Affiliate Manager" при выбранном грейде
// "Management" находит слово "Senior" — оно из другого варианта грейда,
// возможно юзер забыл переключить чип. Раньше эта проверка сравнивала
// название с последней выбранной ПОДСКАЗКОЙ целиком — слишком общо,
// не объясняла, ЧЕМ конкретно название разошлось.
function detectGradeMismatchWord(title, selectedGrade, grades) {
  if (!title.trim() || !selectedGrade) return null;
  const titleLower = title.toLowerCase();
  for (const g of grades) {
    if (g === selectedGrade) continue;
    const words = g.split(/[\s/]+/).filter((w) => w.length > 2);
    for (const w of words) {
      if (titleLower.includes(w.toLowerCase())) return w;
    }
  }
  return null;
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

// closedReason (28.08.2026, макет "15 · Рекрутер — Мои вакансии") —
// бэкенд отдаёт closed_reason ("Нашли кандидата" и т.п.) уже давно
// (см. handle_close_vacancy, guro_id_api.py), но фронт нигде его не
// показывал — макет явно дописывает причину прямо в статус-бейдж
// ("Закрыта — нашли кандидата"). Заодно бейдж переделан с залитой
// пилюли на маленькую точку-индикатор + текст — так в макете.
function StatusBadge({ status, closedReason }) {
  const { t } = useLang();
  const cls = status === "active" ? "vacancy-status-active" : status === "paused" ? "vacancy-status-paused" : "vacancy-status-closed";
  const label = status === "closed" && closedReason
    ? `${t(`vacancies.status.${status}`)} — ${closedReason}`
    : t(`vacancies.status.${status}`);
  return (
    <span className={`vacancy-status-badge ${cls}`}>
      <span className="vacancy-status-dot" />
      {label}
    </span>
  );
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
      {/* Вертикаль/грейд — чипы, как в макете ("Опубликовать вакансию",
          п.2-3 ТЗ), а не выпадающий список — только "Должность" ниже
          остаётся select (в макете это поле "из справочника" с шевроном,
          не набор чипов). 27.08.2026, фидбек владельца: раньше все три
          поля были селектами. */}
      <label>{t("vacancies.form.verticalLabel")}</label>
      <div className="vertical-chips">
        {VERTICALS.map((v) => (
          <button
            key={v}
            type="button"
            className={`vertical-chip${vertical === v ? " is-selected" : ""}`}
            onClick={() => onChange({ vertical: v, grade: "", position: "", positionIsOther: false })}
          >
            {v}
          </button>
        ))}
      </div>

      <label>{t("vacancies.form.gradeLabel")}</label>
      <div className="vertical-chips">
        {gradeOptions.map((g) => (
          <button
            key={g}
            type="button"
            disabled={!vertical}
            className={`vertical-chip${grade === g ? " is-selected" : ""}`}
            onClick={() => onChange({ vertical, grade: g, position: "", positionIsOther: false })}
          >
            {g}
          </button>
        ))}
      </div>

      <label>{t("vacancies.form.positionLabel")}</label>
      {!positionIsOther && (
        <select
          value={position}
          disabled={!vertical || !grade}
          onChange={(e) => onChange({ vertical, grade, position: e.target.value, positionIsOther: false })}
        >
          <option value="">{t("vacancies.form.positionPlaceholder")}</option>
          {positionOptions.map(([code, label]) => (
            <option key={code} value={label}>{label}</option>
          ))}
        </select>
      )}

      {/* "Другое" — отдельная кнопка под селектом (28.08.2026, ТЗ "14 ·
          Рекрутер — Опубликовать вакансию", "+ Другое → свободный ввод"),
          не пункт внутри самого выпадающего списка, как было раньше. */}
      {!positionIsOther ? (
        <button
          type="button"
          className="btn secondary"
          disabled={!vertical || !grade}
          onClick={() => onChange({ vertical, grade, position: "", positionIsOther: true })}
        >
          {t("vacancies.form.positionOther")}
        </button>
      ) : (
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
  salaryVisible: false, description: "",
  durationDays: 30, lang: "ru",
};

function vacancyToForm(v) {
  return {
    title: v.title || "", vertical: v.vertical || "", grade: v.grade || "",
    position: v.position || "", positionIsOther: !!v.position_is_other, location: v.location || "",
    workFormat: v.work_format || "", employmentType: v.employment_type || "",
    salaryFrom: v.salary_from ?? "", salaryTo: v.salary_to ?? "", salaryNegotiable: !!v.salary_negotiable,
    salaryVisible: !!v.salary_visible, description: v.description || "",
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
    setSuggestions([]);
  }

  const mismatchWord = detectGradeMismatchWord(form.title, form.grade, positions.grades);

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
            : error instanceof ApiError && error.code === "DAILY_VACANCY_LIMIT_REACHED"
              ? t("vacancies.form.dailyLimitReached", { date: formatDate(error.details?.resets_at) })
              : error instanceof ApiError && error.code === "ACTIVE_VACANCY_LIMIT_REACHED"
                ? t("vacancies.form.activeLimitReached", { limit: error.details?.limit })
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
                <span>{s.label}</span>
                <span className="partner-meta">{s.vertical} · {s.grade}</span>
              </button>
            ))}
          </div>
        )}
        {mismatchWord && (
          <div className="mismatch-banner">
            ⚠ {t("vacancies.form.mismatchWarning", { word: mismatchWord, grade: form.grade })}
          </div>
        )}

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

        <label>{t("vacancies.form.descriptionLabel")}</label>
        <textarea
          rows={4}
          placeholder={t("vacancies.form.descriptionPlaceholder")}
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
        />

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
// 28.08.2026 (макет "13 · Рекрутер — Вакансии (4 блока)", Untitled-17) —
// приведена в соответствие: бейдж "Официальная вакансия" переехал в
// СВОЮ строку НАД заголовком (был инлайном после текста заголовка),
// вертикаль/грейд/гео/формат/тип занятости стали отдельными чипами
// (были голым текстом через " · "), зарплата — акцентным крупным
// текстом, появилась строка "кто разместил" с аватаром/лого-миниатюрой
// СЛЕВА и рейтинг-кружком СПРАВА (раньше рейтинга на карточке не было
// вообще, хотя бэкенд его уже отдавал — _vacancy_poster_summary,
// guro_id_api.py). employment_type ("Полная"/...) тоже раньше не
// показывался в компактной карточке, хотя бэкенд его отдаёт.
function VacancyCard({ v, onOpen }) {
  const { t } = useLang();
  const salaryText = v.salary_negotiable
    ? t("vacancies.salaryNegotiable")
    : v.salary_from != null || v.salary_to != null
      ? `$${v.salary_from ?? "?"} – $${v.salary_to ?? "?"}`
      : null;
  const days = daysAgo(v.created_at);
  // Премиальное оформление вакансии от лица "Компании" (26.08.2026, ТЗ
  // "Компания. каб", раздел 4) — акцентная рамка + бейдж "Официальная
  // вакансия компании", только у author_workspace=company (у вакансии
  // рекрутера-одиночки — просто имя, без бейджа).
  const isCompany = v.author_workspace === "company";
  const posterName = v.company || v.poster_name;
  const tags = [
    v.vertical, v.grade, v.location,
    v.work_format && t(`vacancies.workFormat.${v.work_format}`),
    v.employment_type && t(`vacancies.employment.${v.employment_type}`),
  ].filter(Boolean);
  return (
    <div
      className={`card vacancy-card${isCompany ? " vacancy-card-company" : ""}`}
      onClick={() => onOpen(v.id)}
      role="button"
      tabIndex={0}
    >
      {isCompany && (
        <div className="vacancy-official-badge">✓ {t("vacancies.officialCompanyBadge")}</div>
      )}
      <h3>{v.title}</h3>
      {tags.length > 0 && (
        <div className="vacancy-tag-row">
          {tags.map((tag, i) => (
            <span className="vacancy-tag-chip" key={i}>{tag}</span>
          ))}
        </div>
      )}
      {salaryText && <div className="vacancy-salary">{salaryText}</div>}
      <div className="vacancy-poster-row">
        <div className="vacancy-poster-avatar">
          {v.poster_logo_url ? <img src={v.poster_logo_url} alt="" /> : initialOf(posterName)}
        </div>
        <div className="vacancy-poster-info">
          <div className="vacancy-poster-name">
            {posterName}
            {v.verified_company && (
              <span className="company-verified-badge" title={t("company.verify.verified")}>✓</span>
            )}
          </div>
          {days != null && (
            <div className="partner-meta">
              {days === 0 ? t("vacancies.postedToday") : t("vacancies.postedAgo", { days })}
            </div>
          )}
        </div>
        {typeof v.reputation_score === "number" && (
          <div className="rating-preview-circle vacancy-poster-rating">{Math.round(v.reputation_score)}</div>
        )}
      </div>
    </div>
  );
}

// Полная карточка (раздел 2.1 ТЗ) — описание скрыто за кнопкой, кнопки
// действий разные для владельца и для остальных.
function VacancyDetail({ id, onBack, onOpenMessages, onManage, onOpenResponses, manageError }) {
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
        <StatusBadge status={v.status} closedReason={v.closed_reason} />
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
            <Msg type="error">{manageError}</Msg>
          </>
        ) : (
          <>
            <button type="button" className="btn secondary" style={{ marginTop: 12 }} onClick={() => onOpenMessages(v.author_id)}>
              {t("vacancies.writeBtn")}
            </button>
            <button type="button" className="btn" style={{ marginTop: 8 }} onClick={onRespond} disabled={respondState.loading || respondState.ok}>
              {respondState.ok ? t("vacancies.respondSentOk") : t("vacancies.applyBtn")}
            </button>
            <Msg type="error">{respondState.error}</Msg>
          </>
        )}
      </div>
    </div>
  );
}

// "Мои вакансии" (раздел 4 ТЗ) — статус/счётчики/действия, тап по строке
// открывает полную карточку (там же кнопки управления).
// vacancies/loading подняты в VacanciesScreen (27.08.2026, ТЗ "экраны по ТЗ
// от 23.08") — те же данные нужны и тут, и для подписи под плиткой
// "Мои вакансии" в верхней навигации (см. NavTiles), незачем грузить дважды.
function MyVacancies({ vacancies, loading, error, onOpen, onManage, onPublish }) {
  const { t } = useLang();

  if (loading) return <Spinner>{t("messages.loading")}</Spinner>;
  if (error) return <Msg type="error">{t("vacancies.loadError")}</Msg>;
  if (!vacancies || vacancies.length === 0) {
    return (
      <div className="card">
        <p className="partner-meta">{t("vacancies.mineEmpty")}</p>
        <button type="button" className="btn" onClick={onPublish}>
          {t("vacancies.publishBtn")}
        </button>
      </div>
    );
  }

  function act(e, action, v) {
    e.stopPropagation();
    onManage(action, v, { stay: true });
  }

  return (
    <div>
      {vacancies.map((v) => (
        <div key={v.id} className="card" style={{ cursor: "pointer" }} onClick={() => onOpen(v.id)}>
          <div className="partner-name">{v.title}</div>
          {/* Тап по телу карточки открывает "Отклики" именно на эту
              вакансию (28.08.2026, макет "15 · Рекрутер — Мои вакансии") —
              раньше вёл на общий экран деталей вакансии. */}
          <div className="vacancy-mine-status-row">
            <StatusBadge status={v.status} closedReason={v.closed_reason} />
            <span className="vacancy-mine-counts">
              👁 {v.views_count} ↩ {v.responses_count}
            </span>
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
        {state.vacancy && (
          <>
            <div className="partner-meta">{state.vacancy.title}</div>
            <div className="partner-meta">
              {t("vacancies.viewsLabel", { n: state.vacancy.views_count })}
              {" · "}
              {t("vacancies.responsesLabel", { n: state.vacancy.responses_count })}
            </div>
          </>
        )}
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

// "Отклики" — плитка верхней навигации (27.08.2026, ТЗ "экраны по ТЗ от
// 23.08", "Вакансии"): агрегация по ВСЕМ своим вакансиям сразу, без захода
// в конкретную — та же логика, что RecruiterResponsesSubscreen.jsx (доступна
// из меню кабинета Рекрутер), но как отдельный вход прямо со вкладки
// "Вакансии" (сама вакансия каждой карточки подписана r.vacancy_title).
function AllResponses({ onBack, onOpenMessages, onOpenHireConfirm }) {
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
    onOpenHireConfirm({
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
        <h3>{t("vacancies.responses.title")}</h3>
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
          <div className="partner-name">{r.vacancy_title}</div>
          <div className="partner-meta">
            {r.candidate_name || (r.candidate_username ? `@${r.candidate_username}` : t("common.noName"))}
            {r.candidate_vertical ? ` · ${r.candidate_vertical}` : ""}
            {typeof r.reputation_score === "number" ? ` · ★ ${r.reputation_score}` : ""}
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

export function VacanciesScreen({ onNavigate, onOpenMessages, onOpenHireConfirm, workspace }) {
  const { t, lang } = useLang();
  const positions = usePositions();
  const [tab, setTab] = useState("board"); // "board" | "mine"
  const [view, setView] = useState({ name: "board" });
  const [caps, setCaps] = useState({ loading: true, recruiter: false, company: false });
  const [refreshKey, setRefreshKey] = useState(0);
  const [manageError, setManageError] = useState(null);

  const [langFilter, setLangFilter] = useState(lang === "en" ? "en" : "ru");
  const [vertical, setVertical] = useState("");
  const [grade, setGrade] = useState("");
  const [position, setPosition] = useState("");
  const [q, setQ] = useState("");
  // Фильтр по тегу "Тип компании" (26.08.2026, ТЗ "Компания. каб", раздел 5)
  // — жёсткий структурный фильтр поверх доски, тот же принцип, что грейд.
  const [companyType, setCompanyType] = useState("");
  const [state, setState] = useState({ loading: true, vacancies: null, truncated: false, error: null });
  // "Мои вакансии" поднято на верхний уровень (27.08.2026, ТЗ "экраны по ТЗ
  // от 23.08") — те же данные нужны и списку под табом, и подписи под
  // плиткой верхней навигации ("N активных · N откликов"), незачем грузить
  // дважды при переключении между табами.
  const [myVac, setMyVac] = useState({ loading: true, vacancies: null, error: null, activeLimit: 0 });

  useEffect(() => {
    Promise.all([
      getMe({ workspace: "recruiter" }).then((d) => !!d.is_recruiter_subscribed).catch(() => false),
      getMe({ workspace: "company" }).then((d) => !!d.is_company_subscribed).catch(() => false),
    ]).then(([recruiter, company]) => setCaps({ loading: false, recruiter, company }));
  }, []);

  function loadMyVacancies() {
    setMyVac((s) => ({ ...s, loading: true, error: null }));
    getMyVacancies()
      .then(({ vacancies, active_vacancies_limit }) => setMyVac({ loading: false, vacancies, error: null, activeLimit: active_vacancies_limit }))
      .catch((error) => setMyVac({ loading: false, vacancies: null, error, activeLimit: 0 }));
  }

  useEffect(loadMyVacancies, [refreshKey]);

  const myVacActiveCount = myVac.vacancies?.filter((v) => v.status === "active").length ?? 0;
  const myVacResponsesTotal = myVac.vacancies?.reduce((sum, v) => sum + (v.responses_count || 0), 0) ?? 0;

  function loadList() {
    setState({ loading: true, vacancies: null, truncated: false, error: null });
    getVacancies({
      lang: langFilter, vertical: vertical || undefined, grade: grade || undefined,
      position: position || undefined, q: q || undefined, companyType: companyType || undefined,
    })
      .then(({ vacancies, truncated }) => setState({ loading: false, vacancies, truncated, error: null }))
      .catch((error) => setState({ loading: false, vacancies: null, truncated: false, error }));
  }

  useEffect(loadList, [langFilter, vertical, grade, position, q, companyType, refreshKey]);

  const canPublish = caps.recruiter || caps.company;
  const subscriptionRequired = state.error instanceof ApiError && state.error.status === 402;

  // stay=true (26.08.2026, ТЗ "рекрутер вакансии", Экран 3) — действия
  // прямо со строки "Мои вакансии" не должны уводить на полную карточку,
  // остаёмся в списке (в отличие от тех же действий с экрана детали).
  async function onManage(action, v, { stay } = {}) {
    setManageError(null);
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
    } catch (error) {
      haptic("error");
      setManageError(
        error instanceof ApiError && error.code === "ACTIVE_VACANCY_LIMIT_REACHED"
          ? t("vacancies.form.activeLimitReached", { limit: error.details?.limit })
          : t("vacancies.loadError"),
      );
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
        onOpenResponses={(id) => setView({ name: "responses", id, returnTo: "detail" })}
        manageError={manageError}
      />
    );
  }

  // returnTo (28.08.2026, макет "15 · Рекрутер — Мои вакансии") — "Отклики"
  // теперь открывается ДВУМЯ путями: кнопкой на VacancyDetail (returnTo=
  // "detail", как раньше) И тапом по телу карточки в "Мои вакансии"
  // (returnTo="board" — макет: "Тап по телу карточки открывает отклики
  // именно на эту вакансию", минуя промежуточный экран детали). "Назад"
  // должен вернуть туда, откуда реально пришли, а не всегда в деталь.
  if (view.name === "responses") {
    return (
      <VacancyResponses
        vacancyId={view.id}
        onBack={() => {
          setView({ name: view.returnTo || "detail", id: view.id });
          if (view.returnTo === "board") setRefreshKey((k) => k + 1);
        }}
        onOpenMessages={onOpenMessages}
        onOpenHireConfirm={onOpenHireConfirm}
      />
    );
  }

  if (view.name === "all-responses") {
    return (
      <AllResponses
        onBack={() => setView({ name: "board" })}
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
        <div className="project-head">
          <h3>{t("vacancies.title")}</h3>
          <WorkspaceCabinetBadge workspace={workspace} />
        </div>
        <div className="partner-meta" style={{ marginBottom: 10 }}>{t("vacancies.hint")}</div>

        {/* Верхняя навигация плитками 2×2 (27.08.2026, ТЗ "экраны по ТЗ от
            23.08", "Вакансии") — вместо старого 2-таб переключателя.
            "Мои вакансии"/"Отклики"/"+Опубликовать" доступны только тем, у
            кого есть публикующая подписка (Рекрутер/Компания) — те же
            условия, что у старой кнопки "Опубликовать" ниже. */}
        <div className="vacancy-nav-grid">
          <button
            type="button"
            className={`vacancy-nav-tile${tab === "board" ? " is-active" : ""}`}
            onClick={() => setTab("board")}
          >
            <span className="vacancy-nav-tile-title">{t("vacancies.tabBoard")}</span>
            <span className="vacancy-nav-tile-sub">{t("vacancies.navBoardHint")}</span>
          </button>
          {/* Порядок плиток — сверен ещё раз по РЕНДЕРУ макета "13 · Рекрутер
              — Вакансии (4 блока)" (28.08.2026): верхний ряд Доска|Мои
              вакансии, нижний Отклики|+Опубликовать (предыдущее чтение
              этого же макета дало обратный порядок строк — при сверке с
              картинкой, а не только текстовым слоем PDF, верным
              оказался этот). Активная плитка (Доска/Мои вакансии) — та,
              что залита цветом на макете; "+Опубликовать" там обычная
              нейтральная плитка, а не всегда-зелёная, как было. */}
          {canPublish && (
            <button
              type="button"
              className={`vacancy-nav-tile${tab === "mine" ? " is-active" : ""}`}
              onClick={() => setTab("mine")}
            >
              <span className="vacancy-nav-tile-title">{t("vacancies.tabMine")}</span>
              <span className="vacancy-nav-tile-sub">
                {t("vacancies.navMineHint", { active: myVacActiveCount, responses: myVacResponsesTotal })}
              </span>
            </button>
          )}
          {canPublish && (
            <button type="button" className="vacancy-nav-tile" onClick={() => setView({ name: "all-responses" })}>
              <span className="vacancy-nav-tile-title">{t("vacancies.responses.title")}</span>
              <span className="vacancy-nav-tile-sub">{t("vacancies.navResponsesHint")}</span>
            </button>
          )}
          {canPublish && (
            <button
              type="button"
              className="vacancy-nav-tile"
              onClick={() => setView({ name: "form" })}
            >
              <span className="vacancy-nav-tile-title">{t("vacancies.publishBtn")}</span>
              <span className="vacancy-nav-tile-sub">{t("vacancies.navPublishHint")}</span>
            </button>
          )}
        </div>
        {!canPublish && !caps.loading && (
          <div className="partner-meta" style={{ marginTop: 10 }}>{t("vacancies.upsellText")}</div>
        )}

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
            <select value={companyType} onChange={(e) => setCompanyType(e.target.value)} style={{ marginTop: 8 }}>
              <option value="">{t("company.types.filterAll")}</option>
              {COMPANY_TYPES.map((k) => (
                <option key={k} value={k}>{t(`company.types.${k}`)}</option>
              ))}
            </select>
            <input
              type="text"
              placeholder={t("vacancies.searchPlaceholder")}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ marginTop: 8 }}
            />
          </>
        )}

      </div>

      {tab === "mine" && (
        <>
          {/* Бейдж "N из M активных" в шапке (27.08.2026, ТЗ "экраны по ТЗ
              от 23.08") — activeLimit=0, пока capability-фактические
              подписки ещё грузятся/отсутствуют, тогда бейдж просто не
              показываем (незачем пугать "0 из 0"). */}
          {myVac.activeLimit > 0 && (
            <div className="card">
              <div className="project-head">
                <h3>{t("vacancies.tabMine")}</h3>
                <span className="chip">{t("vacancies.mineActiveBadge", { active: myVacActiveCount, limit: myVac.activeLimit })}</span>
              </div>
            </div>
          )}
          <Msg type="error">{manageError}</Msg>
          <MyVacancies
            vacancies={myVac.vacancies}
            loading={myVac.loading}
            error={myVac.error}
            onOpen={(id) => setView({ name: "responses", id, returnTo: "board" })}
            onManage={onManage}
            onPublish={() => setView({ name: "form" })}
          />
        </>
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
