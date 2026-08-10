import { EditableField } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";

export function OffersSubscreen({ profile, privacy, onPrivacyChange, onFieldSaved, onBack }) {
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        ‹ Профиль
      </button>
      <div className="card">
        <h3>Мои офферы</h3>
        <label>Я ищу</label>
        {profile.looking_for ? (
          <div className="editable-field-value">{profile.looking_for}</div>
        ) : (
          <div className="editable-field-empty">
            не указано — заполняется в анкете @GamblingCommunitybot
          </div>
        )}
        <EditableField
          field="offering"
          label="Я полезен"
          placeholder="Например: могу подключить трафик, есть база рекламодателей…"
          value={profile.offering}
          multiline
          onSaved={(v) => onFieldSaved("offering", v)}
        />
      </div>
      <PrivacyToggles
        privacy={privacy}
        onChange={onPrivacyChange}
        fields={["show_offers"]}
        hint="Управляет показом обоих полей разом — «ищу» и «полезен»."
      />
    </div>
  );
}
