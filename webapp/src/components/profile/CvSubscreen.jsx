import { EditableField } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { useLang } from "../../i18n.jsx";

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
      </div>
      <PrivacyToggles
        privacy={privacy}
        onChange={onPrivacyChange}
        fields={["show_cv"]}
        hint={t("cv.privacyHint")}
      />
    </div>
  );
}
