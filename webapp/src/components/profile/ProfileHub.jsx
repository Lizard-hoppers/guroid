import { addToHomeScreen, canAddToHomeScreen, getAvatarUrl, haptic } from "../../telegram.js";
import { initialOf, pluralRu } from "../../utils.js";
import { CharacteristicButton, RatingCard, WorkStatusPicker } from "../Shared.jsx";
import { useLang } from "../../i18n.jsx";

// Порядок пунктов — по макету владельца ("рейтинг порядок.pdf", 16.08.2026):
// Офферы, Сообщения, Рейтинг, QR, CV, Контакты.
const MENU = [
  { key: "offers", labelKey: "hub.menu.offers" },
  { key: "messages", labelKey: "hub.menu.messages" },
  { key: "rating", labelKey: "hub.menu.rating" },
  { key: "qr", labelKey: "hub.menu.qr" },
  { key: "cv", labelKey: "hub.menu.cv" },
  { key: "contacts", labelKey: "hub.menu.contacts" },
];

// "Первый шаг" (28.08.2026, макет "01 · Профиль (личный)") — видна, пока
// у пользователя 0 подтверждённых партнёрств: вместо голого "рейтинг 0"
// сразу даёт действие. Ведёт на таб "Сделки" (onNavigateTab — тот же
// проп, что уже передаётся в RecruiterHub/CompanyHub, см. App.jsx).
function FirstStepCard({ onNavigateTab }) {
  const { t } = useLang();
  return (
    <div className="card first-step-card">
      <span className="section-eyebrow">{t("hub.firstStep.eyebrow")}</span>
      <h3>{t("hub.firstStep.title")}</h3>
      <p className="partner-meta">{t("hub.firstStep.text")}</p>
      <button type="button" className="btn" onClick={() => onNavigateTab?.("confirm")}>
        {t("hub.firstStep.cta")}
      </button>
    </div>
  );
}

// Главная страница профиля — визитка (аватар/имя/должность/компания/
// вертикаль) + меню из разделов. Метрики/партнёры/CV/контакты/офферы
// раньше были на одном экране, теперь разнесены по своим под-экранам
// (см. profile/*.jsx), сюда попадает только сама визитка.
export function ProfileHub({ profile, onNavigateSub, onNavigateTab, onWorkStatusChange }) {
  const { t, lang } = useLang();
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
        </div>
        {(profile.vertical || profile.days_in_community != null) && (
          <div className="profile-meta-row">
            {profile.vertical && <span className="profile-vertical-badge">{profile.vertical}</span>}
            {profile.days_in_community != null && (
              <span className="profile-tenure-badge">
                🗓 {t("hub.daysInCommunity", {
                  count: profile.days_in_community,
                  unit: lang === "ru"
                    ? pluralRu(profile.days_in_community, ["день", "дня", "дней"])
                    : profile.days_in_community === 1 ? "day" : "days",
                })}
              </span>
            )}
          </div>
        )}
        <div className="work-status-section">
          <label>{t("hub.status")}</label>
          <WorkStatusPicker value={profile.work_status} onChange={onWorkStatusChange} />
        </div>
        {/* «Характеристика» (26.08.2026) — та же кнопка, что видят чужие
            подписчики на моей карточке в поиске (см. SearchScreen.jsx), тут
            как превью своих данных. ВАЖНО: /api/me отдаёт свои поля ВСЕГДА
            полностью, независимо от тумблеров приватности — это НЕ точная
            копия того, что видит чужой (тот гейтится show_cv/show_offers),
            а просто "вот что там внутри", если понадобится свериться. */}
        <CharacteristicButton profile={profile} />
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
            📲 <span className="link-underline">{t("hub.addToHome")}</span>
          </button>
        )}
      </div>

      <RatingCard
        reputation={profile.reputation_score}
        tier={profile.reputation_tier}
        partnerships={profile.confirmed_partnerships}
        daysInCommunity={profile.days_in_community}
      />

      {(profile.confirmed_partnerships ?? 0) === 0 && <FirstStepCard onNavigateTab={onNavigateTab} />}

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
    </div>
  );
}
