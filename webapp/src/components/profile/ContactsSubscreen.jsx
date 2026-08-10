import { EditableField } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";

export function ContactsSubscreen({ profile, privacy, onPrivacyChange, onFieldSaved, onBack }) {
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        ‹ Профиль
      </button>
      <div className="card">
        <h3>Мои контакты</h3>
        <div className="partner-meta">Telegram: @{profile.username}</div>
        {profile.linkedin ? (
          <div className="partner-meta" style={{ marginTop: 8 }}>
            LinkedIn: {profile.linkedin}
          </div>
        ) : (
          <div className="editable-field-empty" style={{ marginTop: 8 }}>
            LinkedIn не указан в анкете
          </div>
        )}
        <EditableField
          field="website"
          label="Сайт"
          placeholder="example.com"
          value={profile.website}
          onSaved={(v) => onFieldSaved("website", v)}
        />
      </div>
      <PrivacyToggles
        privacy={privacy}
        onChange={onPrivacyChange}
        fields={["show_contacts"]}
        hint="Управляет показом LinkedIn и сайта. Telegram виден всегда — иначе вас не найти в поиске."
      />
    </div>
  );
}
