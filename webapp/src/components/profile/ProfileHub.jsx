import { addToHomeScreen, canAddToHomeScreen, getAvatarUrl, haptic } from "../../telegram.js";
import { initialOf } from "../../utils.js";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { RatingPreview, RatingSummaryLine, WorkStatusPicker } from "../Shared.jsx";
import { useLang } from "../../i18n.jsx";

const MENU = [
  { key: "rating", labelKey: "hub.menu.rating" },
  { key: "cv", labelKey: "hub.menu.cv" },
  { key: "contacts", labelKey: "hub.menu.contacts" },
  { key: "offers", labelKey: "hub.menu.offers" },
  { key: "messages", labelKey: "hub.menu.messages" },
  { key: "qr", labelKey: "hub.menu.qr" },
];

// Главная страница профиля — визитка (аватар/имя/должность/компания/
// вертикаль) + меню из разделов. Метрики/партнёры/CV/контакты/офферы
// раньше были на одном экране, теперь разнесены по своим под-экранам
// (см. profile/*.jsx), сюда попадает только сама визитка.
export function ProfileHub({ profile, privacy, onPrivacyChange, onNavigateSub, onWorkStatusChange }) {
  const { t } = useLang();
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
            <h2>{profile.name || (profile.username ? `@${profile.username}` : t("common.noName"))}</h2>
            {profile.profession && <div className="profile-header-sub">{profile.profession}</div>}
            {profile.company && <div className="profile-header-sub">{profile.company}</div>}
          </div>
          <RatingPreview
            reputation={profile.reputation_score}
            onOpen={() => onNavigateSub("rating")}
          />
        </div>
        <RatingSummaryLine
          reputation={profile.reputation_score}
          partnerships={profile.confirmed_partnerships}
          isSubscribed={profile.is_subscribed}
          onOpen={() => onNavigateSub("rating")}
        />
        {profile.vertical && <span className="profile-vertical-badge">{profile.vertical}</span>}
        <div className="work-status-section">
          <label>{t("hub.status")}</label>
          <WorkStatusPicker value={profile.work_status} onChange={onWorkStatusChange} />
        </div>
        {canAddToHomeScreen() && (
          <button
            type="button"
            className="onboarding-more-link"
            style={{ marginTop: 12 }}
            onClick={() => {
              haptic("light");
              addToHomeScreen();
            }}
          >
            <span className="no-underline">📲</span> {t("hub.addToHome")}
          </button>
        )}
      </div>

      <div className="card">
        {MENU.map((m) => (
          <button
            key={m.key}
            type="button"
            className="profile-menu-item"
            onClick={() => onNavigateSub(m.key)}
          >
            <span>
              {t(m.labelKey)}
              {m.key === "messages" && profile.unread_messages > 0 && (
                <span className="thread-unread-badge">{profile.unread_messages}</span>
              )}
            </span>
            <span className="profile-menu-item-chevron">›</span>
          </button>
        ))}
      </div>

      <PrivacyToggles
        privacy={privacy}
        onChange={onPrivacyChange}
        fields={["show_name", "show_company", "show_vertical", "show_profession"]}
        hint={t("hub.privacyHint")}
      />
    </div>
  );
}
