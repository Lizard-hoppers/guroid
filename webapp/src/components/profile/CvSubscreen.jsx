import { EditableField } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";

export function CvSubscreen({ profile, privacy, onPrivacyChange, onFieldSaved, onBack }) {
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        ‹ Профиль
      </button>
      <div className="card">
        <h3>Моё CV</h3>
        <EditableField
          field="cv_text"
          label="Опыт и навыки"
          placeholder="Например: 5 лет в iGaming, руководил командой из 10 человек…"
          value={profile.cv_text}
          multiline
          onSaved={(v) => onFieldSaved("cv_text", v)}
        />
      </div>
      <PrivacyToggles
        privacy={privacy}
        onChange={onPrivacyChange}
        fields={["show_cv"]}
        hint="Пока выключено — CV не видно тем, кто ищет вас в GURO ID."
      />
    </div>
  );
}
