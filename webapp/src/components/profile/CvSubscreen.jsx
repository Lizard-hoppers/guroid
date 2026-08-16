import { useEffect, useState } from "react";
import { EditableField, Msg } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { useLang } from "../../i18n.jsx";
import { haptic } from "../../telegram.js";
import {
  ApiError, setCvField, setCvProfession, setCvGrade, setCvFlag, setCvSalary,
  addCvExperience, deleteCvExperience,
} from "../../api.js";

// Расширение "Моё CV" (12.08.2026, по макету владельца "2Правки СV.pdf").
// Те же канонические списки, что в VacanciesScreen.jsx/SearchScreen.jsx —
// намеренно продублированы (тот же приём, уже принят в проекте), т.к.
// список грейдов тут ДРУГОЙ (буквально из макета CV, не из constants.GRADES).
const CV_VERTICALS = ["Gambling", "Betting", "Crypto", "Dating", "E-Commerce", "FinTech", "Nutra", "Other"];
const CV_GRADE_LEVELS = [
  "Junior (0–2 years)", "Mid (2–5 years)", "Senior (5–8 years)",
  "Lead (8+ years)", "Head / Director", "C-Level / VP",
];
const CV_EXPERIENCE_MAX = 20;

function ProfessionField({ value, onSaved }) {
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
    const trimmed = draft.trim();
    if (!trimmed) {
      setError(t("cv.profession.required"));
      return;
    }
    setSaving(true);
    setError("");
    try {
      const updated = await setCvProfession(trimmed);
      onSaved(updated.cv_profession);
      setEditing(false);
      haptic("success");
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === "CHANGE_LIMIT_REACHED"
          ? t("cv.profession.limitReached")
          : t("common.saveError"),
      );
      haptic("error");
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <div className="editable-field">
        <label>{t("cv.profession.label")}</label>
        <input type="text" value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus disabled={saving} />
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
      <label>{t("cv.profession.label")}</label>
      {value ? (
        <div className="editable-field-value">{value}</div>
      ) : (
        <div className="editable-field-empty">{t("common.notFilled")}</div>
      )}
      <div className="partner-meta">{t("cv.profession.limitHint")}</div>
      <button className="btn secondary" style={{ marginTop: 8 }} onClick={startEdit}>
        {value ? t("common.edit") : t("common.fill")}
      </button>
    </div>
  );
}

function VerticalsField({ value, onSaved }) {
  const { t } = useLang();
  const [saving, setSaving] = useState(false);
  const selected = value ? value.split(",").map((s) => s.trim()).filter(Boolean) : [];

  async function toggle(v) {
    if (saving) return;
    const next = selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v];
    setSaving(true);
    try {
      const updated = await setCvField("cv_verticals", next.join(", "));
      onSaved(updated.cv_verticals);
      haptic("select");
    } catch {
      haptic("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <h3>{t("cv.verticals.title")}</h3>
      <div className="vertical-chips">
        {CV_VERTICALS.map((v) => (
          <button
            key={v}
            type="button"
            disabled={saving}
            className={`vertical-chip${selected.includes(v) ? " is-selected" : ""}`}
            onClick={() => toggle(v)}
          >
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}

function GradeField({ value, onSaved }) {
  const { t } = useLang();
  const [saving, setSaving] = useState(false);

  async function change(v) {
    setSaving(true);
    try {
      const updated = await setCvGrade(v || null);
      onSaved(updated.cv_grade);
      haptic("select");
    } catch {
      haptic("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <h3>{t("cv.grade.title")}</h3>
      <select value={value || ""} disabled={saving} onChange={(e) => change(e.target.value)}>
        <option value="">{t("cv.grade.placeholder")}</option>
        {CV_GRADE_LEVELS.map((g) => (
          <option key={g} value={g}>{g}</option>
        ))}
      </select>
    </div>
  );
}

function TriStateField({ title, field, value, onSaved }) {
  const { t } = useLang();
  const [saving, setSaving] = useState(false);

  async function pick(next) {
    if (saving || next === value) return;
    setSaving(true);
    try {
      const updated = await setCvFlag(field, next);
      onSaved(updated[field]);
      haptic("select");
    } catch {
      haptic("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <h3>{title}</h3>
      <div className="tristate-picker">
        <button
          type="button"
          className={`tristate-option${value === true ? " active" : ""}`}
          disabled={saving}
          onClick={() => pick(true)}
        >
          {t("common.yes")}
        </button>
        <button
          type="button"
          className={`tristate-option${value === false ? " active" : ""}`}
          disabled={saving}
          onClick={() => pick(false)}
        >
          {t("common.no")}
        </button>
        <button
          type="button"
          className={`tristate-option${value == null ? " active" : ""}`}
          disabled={saving}
          onClick={() => pick(null)}
        >
          {t("common.notSpecified")}
        </button>
      </div>
    </div>
  );
}

function SalaryField({ salaryFrom, salaryTo, negotiable, onSaved }) {
  const { t } = useLang();
  const [draft, setDraft] = useState({ from: salaryFrom ?? "", to: salaryTo ?? "", negotiable: !!negotiable });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setSaving(true);
    setError("");
    try {
      const updated = await setCvSalary({
        salaryFrom: draft.negotiable ? null : draft.from || null,
        salaryTo: draft.negotiable ? null : draft.to || null,
        negotiable: draft.negotiable,
      });
      onSaved(updated);
      haptic("success");
    } catch {
      setError(t("common.saveError"));
      haptic("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <h3>{t("cv.salary.title")}</h3>
      <div className="amount-row">
        <input
          type="number"
          inputMode="decimal"
          placeholder={t("cv.salary.fromPlaceholder")}
          value={draft.from}
          disabled={draft.negotiable || saving}
          onChange={(e) => setDraft((d) => ({ ...d, from: e.target.value }))}
        />
        <input
          type="number"
          inputMode="decimal"
          placeholder={t("cv.salary.toPlaceholder")}
          value={draft.to}
          disabled={draft.negotiable || saving}
          onChange={(e) => setDraft((d) => ({ ...d, to: e.target.value }))}
        />
      </div>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={draft.negotiable}
          disabled={saving}
          onChange={(e) => setDraft((d) => ({ ...d, negotiable: e.target.checked }))}
        />
        {t("cv.salary.negotiableLabel")}
      </label>
      <button className="btn" style={{ marginTop: 10 }} onClick={save} disabled={saving}>
        {saving ? t("common.saving") : t("common.save")}
      </button>
      <Msg type="error">{error}</Msg>
    </div>
  );
}

const EMPTY_EXPERIENCE = { company: "", position: "", date_from: "", date_to: "", location: "", description: "" };

function ExperienceForm({ onAdded, onCancel }) {
  const { t } = useLang();
  const [form, setForm] = useState(EMPTY_EXPERIENCE);
  const [state, setState] = useState({ loading: false, error: null });

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function onSubmit(e) {
    e.preventDefault();
    if (!form.company.trim() || !form.position.trim()) {
      setState({ loading: false, error: t("cv.experience.form.required") });
      return;
    }
    setState({ loading: true, error: null });
    try {
      const entry = await addCvExperience({
        company: form.company.trim(),
        position: form.position.trim(),
        date_from: form.date_from || null,
        date_to: form.date_to || null,
        location: form.location || null,
        description: form.description || null,
      });
      haptic("success");
      onAdded(entry);
    } catch (err) {
      setState({
        loading: false,
        error: err instanceof ApiError && err.code === "LIMIT_REACHED"
          ? t("cv.experience.limitReached")
          : t("common.saveError"),
      });
      haptic("error");
    }
  }

  return (
    <form onSubmit={onSubmit} style={{ marginTop: 12 }}>
      <label>{t("cv.experience.form.companyLabel")}</label>
      <input
        type="text"
        value={form.company}
        onChange={(e) => set("company", e.target.value)}
        placeholder={t("cv.experience.form.companyPlaceholder")}
      />
      <label>{t("cv.experience.form.positionLabel")}</label>
      <input
        type="text"
        value={form.position}
        onChange={(e) => set("position", e.target.value)}
        placeholder={t("cv.experience.form.positionPlaceholder")}
      />
      <label>{t("cv.experience.form.datesLabel")}</label>
      <div className="amount-row">
        <input
          type="text"
          value={form.date_from}
          onChange={(e) => set("date_from", e.target.value)}
          placeholder={t("cv.experience.form.dateFromPlaceholder")}
        />
        <input
          type="text"
          value={form.date_to}
          onChange={(e) => set("date_to", e.target.value)}
          placeholder={t("cv.experience.form.dateToPlaceholder")}
        />
      </div>
      <label>{t("cv.experience.form.locationLabel")}</label>
      <input
        type="text"
        value={form.location}
        onChange={(e) => set("location", e.target.value)}
        placeholder={t("cv.experience.form.locationPlaceholder")}
      />
      <label>{t("cv.experience.form.descriptionLabel")}</label>
      <textarea
        rows={3}
        value={form.description}
        onChange={(e) => set("description", e.target.value)}
        placeholder={t("cv.experience.form.descriptionPlaceholder")}
      />
      <button className="btn" type="submit" disabled={state.loading}>
        {state.loading ? t("common.saving") : t("common.save")}
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
      <Msg type="error">{state.error}</Msg>
    </form>
  );
}

function ExperienceList({ entries, onChange }) {
  const { t } = useLang();
  const [showForm, setShowForm] = useState(false);
  const [items, setItems] = useState(entries || []);
  const [deletingId, setDeletingId] = useState(null);

  // держим items в синхроне, если profile перезагрузился (напр. re-mount экрана)
  useEffect(() => {
    setItems(entries || []);
  }, [entries]);

  async function onDelete(id) {
    setDeletingId(id);
    try {
      await deleteCvExperience(id);
      const next = items.filter((it) => it.id !== id);
      setItems(next);
      onChange(next);
      haptic("light");
    } catch {
      haptic("error");
    } finally {
      setDeletingId(null);
    }
  }

  function onAdded(entry) {
    const next = [entry, ...items];
    setItems(next);
    onChange(next);
    setShowForm(false);
  }

  return (
    <div className="card">
      <h3>{t("cv.experience.title")}</h3>
      {items.length === 0 && <div className="partner-meta">{t("cv.experience.empty")}</div>}
      {items.map((it) => (
        <div key={it.id} className="partner-row" style={{ alignItems: "center" }}>
          <div className="partner-info">
            <div className="partner-name">{[it.position, it.company].filter(Boolean).join(" — ")}</div>
            <div className="partner-meta">
              {(it.date_from || it.date_to) &&
                `${it.date_from || "?"} – ${it.date_to || t("cv.experience.present")}`}
              {it.location ? ` · ${it.location}` : ""}
            </div>
            {it.description && <div className="partner-meta">{it.description}</div>}
          </div>
          <button
            type="button"
            className="btn secondary"
            style={{ width: "auto", padding: "8px 14px" }}
            onClick={() => onDelete(it.id)}
            disabled={deletingId === it.id}
          >
            {t("common.delete")}
          </button>
        </div>
      ))}
      {items.length < CV_EXPERIENCE_MAX ? (
        showForm ? (
          <ExperienceForm onAdded={onAdded} onCancel={() => setShowForm(false)} />
        ) : (
          <button type="button" className="btn secondary" style={{ marginTop: 10 }} onClick={() => setShowForm(true)}>
            {t("cv.experience.addBtn")}
          </button>
        )
      ) : (
        <div className="partner-meta">{t("cv.experience.limitReached")}</div>
      )}
    </div>
  );
}

export function CvSubscreen({ profile, privacy, onPrivacyChange, onFieldSaved, onBack }) {
  const { t } = useLang();
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>

      <div className="card">
        <h3>{t("cv.title")}</h3>
        <EditableField
          field="cv_text"
          label={t("cv.label")}
          placeholder={t("cv.placeholder")}
          value={profile.cv_text}
          multiline
          onSaved={(v) => onFieldSaved("cv_text", v)}
        />
        <ProfessionField value={profile.cv_profession} onSaved={(v) => onFieldSaved("cv_profession", v)} />
        <EditableField
          field="cv_location"
          label={t("cv.location.label")}
          placeholder={t("cv.location.placeholder")}
          value={profile.cv_location}
          saveField={setCvField}
          onSaved={(v) => onFieldSaved("cv_location", v)}
        />
      </div>

      <VerticalsField value={profile.cv_verticals} onSaved={(v) => onFieldSaved("cv_verticals", v)} />
      <GradeField value={profile.cv_grade} onSaved={(v) => onFieldSaved("cv_grade", v)} />
      <TriStateField
        title={t("cv.relocation.title")}
        field="cv_relocation_ready"
        value={profile.cv_relocation_ready}
        onSaved={(v) => onFieldSaved("cv_relocation_ready", v)}
      />
      <TriStateField
        title={t("cv.polygraph.title")}
        field="cv_polygraph_consent"
        value={profile.cv_polygraph_consent}
        onSaved={(v) => onFieldSaved("cv_polygraph_consent", v)}
      />
      <SalaryField
        salaryFrom={profile.cv_salary_from}
        salaryTo={profile.cv_salary_to}
        negotiable={profile.cv_salary_negotiable}
        onSaved={(updated) => {
          onFieldSaved("cv_salary_from", updated.cv_salary_from);
          onFieldSaved("cv_salary_to", updated.cv_salary_to);
          onFieldSaved("cv_salary_negotiable", updated.cv_salary_negotiable);
        }}
      />

      <div className="card">
        <h3>{t("cv.skills.title")}</h3>
        <EditableField
          field="cv_skills"
          label={t("cv.skills.label")}
          placeholder={t("cv.skills.placeholder")}
          value={profile.cv_skills}
          saveField={setCvField}
          onSaved={(v) => onFieldSaved("cv_skills", v)}
        />
        <EditableField
          field="cv_languages"
          label={t("cv.languages.label")}
          placeholder={t("cv.languages.placeholder")}
          value={profile.cv_languages}
          saveField={setCvField}
          onSaved={(v) => onFieldSaved("cv_languages", v)}
        />
        <EditableField
          field="cv_certifications"
          label={t("cv.certifications.label")}
          placeholder={t("cv.certifications.placeholder")}
          value={profile.cv_certifications}
          saveField={setCvField}
          onSaved={(v) => onFieldSaved("cv_certifications", v)}
        />
      </div>

      <ExperienceList
        entries={profile.cv_experience}
        onChange={(next) => onFieldSaved("cv_experience", next)}
      />

      <PrivacyToggles
        privacy={privacy}
        onChange={onPrivacyChange}
        fields={["show_cv"]}
        hint={t("cv.privacyHint")}
      />
    </div>
  );
}
