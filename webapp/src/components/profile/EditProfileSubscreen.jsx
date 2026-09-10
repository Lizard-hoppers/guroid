import { useState } from "react";
import { setAnketaField } from "../../api.js";
import { EditableField, Msg } from "../Shared.jsx";
import { useLang } from "../../i18n.jsx";
import { haptic } from "../../telegram.js";

// Правка САМОЙ анкеты прямо в приложении (09.09.2026, просьба владельца).
// Раньше эти поля заполнял только бот при регистрации, а Mini App их читал.
//
// Имя, компания и должность — свободный текст. Вертикаль и грейд — списком:
// сервер принимает их только из справочника, потому что по ним работает
// поиск (browse сравнивает вертикаль с каноническим значением, грейд ищется
// подстрокой). Раз выбор всё равно ограничен, честнее показать список, чем
// дать ввести что угодно и ответить отказом.
//
// Справочники продублированы здесь как константы, а не запрошены с сервера:
// это неизменные списки из constants.py, отдельный запрос ради них означал
// бы лишнее ожидание на экране, который открывают ради двух правок.
const VERTICALS = [
  "Gambling", "Betting", "Crypto", "Dating", "E-Commerce", "FinTech", "Nutra", "Other",
];
const GRADES = [
  "C-Level", "Head of / Director", "Management", "Senior", "Specialist", "Junior / Entry",
];

function ChoiceField({ field, label, value, options, onSaved }) {
  const { t } = useLang();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function change(next) {
    setSaving(true);
    setError("");
    try {
      await setAnketaField(field, next);
      onSaved(field, next || null);
      haptic("success");
    } catch {
      setError(t("common.saveError"));
      haptic("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <label>{label}</label>
      <select value={value || ""} disabled={saving} onChange={(e) => change(e.target.value)}>
        <option value="">{t("editProfile.choosePlaceholder")}</option>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
      <Msg type="error">{error}</Msg>
    </>
  );
}

export function EditProfileSubscreen({ profile, onFieldSaved, onBack }) {
  const { t } = useLang();
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>

      <div className="card">
        <h3>{t("editProfile.title")}</h3>
        <EditableField
          field="name"
          label={t("editProfile.name")}
          value={profile.name}
          saveField={setAnketaField}
          onSaved={(v) => onFieldSaved("name", v)}
        />
        <EditableField
          field="company"
          label={t("editProfile.company")}
          value={profile.company}
          saveField={setAnketaField}
          onSaved={(v) => onFieldSaved("company", v)}
        />
        <EditableField
          field="profession"
          label={t("editProfile.profession")}
          value={profile.profession}
          saveField={setAnketaField}
          onSaved={(v) => onFieldSaved("profession", v)}
        />

        <ChoiceField
          field="vertical"
          label={t("editProfile.vertical")}
          value={profile.vertical}
          options={VERTICALS}
          onSaved={onFieldSaved}
        />
        <ChoiceField
          field="grade"
          label={t("editProfile.grade")}
          value={profile.grade}
          options={GRADES}
          onSaved={onFieldSaved}
        />
        <div className="privacy-hint" style={{ marginTop: 12 }}>
          {t("editProfile.verticalHint")}
        </div>
      </div>

      {/* Про юзернейм и страну сказано прямо здесь, чтобы человек не искал,
          где их поменять, и не решил, что это недоделка. */}
      <div className="card">
        <div className="privacy-hint" style={{ marginBottom: 0 }}>
          {t("editProfile.lockedHint")}
        </div>
      </div>
    </div>
  );
}
