import { getAvatarUrl } from "../../telegram.js";
import { initialOf } from "../../utils.js";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { WorkStatusPicker } from "../Shared.jsx";

const MENU = [
  { key: "rating", label: "Мой рейтинг" },
  { key: "cv", label: "Моё CV" },
  { key: "contacts", label: "Мои контакты" },
  { key: "offers", label: "Мои офферы" },
  { key: "qr", label: "Мой QR" },
];

// Главная страница профиля — визитка (аватар/имя/должность/компания/
// вертикаль) + меню из 4 разделов. Метрики/партнёры/CV/контакты/офферы
// раньше были на одном экране, теперь разнесены по своим под-экранам
// (см. profile/*.jsx), сюда попадает только сама визитка.
export function ProfileHub({ profile, privacy, onPrivacyChange, onNavigateSub, onWorkStatusChange }) {
  const avatarUrl = getAvatarUrl();
  return (
    <div>
      <div className="card">
        <div className="profile-header-card">
          {avatarUrl ? (
            <img className="profile-avatar" src={avatarUrl} alt="" />
          ) : (
            <div className="profile-avatar-fallback">{initialOf(profile.name, profile.username)}</div>
          )}
          <div className="profile-header-info">
            <h2>{profile.name || (profile.username ? `@${profile.username}` : "Без имени")}</h2>
            {profile.profession && <div className="profile-header-sub">{profile.profession}</div>}
            {profile.company && <div className="profile-header-sub">{profile.company}</div>}
          </div>
        </div>
        {profile.vertical && <span className="profile-vertical-badge">{profile.vertical}</span>}
        <div className="work-status-section">
          <label>Статус</label>
          <WorkStatusPicker value={profile.work_status} onChange={onWorkStatusChange} />
        </div>
      </div>

      <div className="card">
        {MENU.map((m) => (
          <button
            key={m.key}
            type="button"
            className="profile-menu-item"
            onClick={() => onNavigateSub(m.key)}
          >
            <span>{m.label}</span>
            <span className="profile-menu-item-chevron">›</span>
          </button>
        ))}
      </div>

      <PrivacyToggles
        privacy={privacy}
        onChange={onPrivacyChange}
        fields={["show_name", "show_company", "show_vertical", "show_profession"]}
        hint="Эти поля видны в вашей визитке тем, кто ищет вас в GURO ID. По умолчанию скрыты — включите то, что хотите показать."
      />
    </div>
  );
}
