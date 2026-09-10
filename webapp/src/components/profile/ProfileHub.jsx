import { addToHomeScreen, canAddToHomeScreen, getAvatarUrl, haptic } from "../../telegram.js";
import { initialOf, pluralRu } from "../../utils.js";
import { CharacteristicButton, RatingCard, TurnoverCard, WorkStatusPicker } from "../Shared.jsx";
import { useLang } from "../../i18n.jsx";
import { IconShare } from "../Icons.jsx";

// Иконки пунктов меню (05.09.2026, сверка с макетом "01 · Профиль
// (личный)"): лаймовый контур 20x20, рисуются инлайном тем же приёмом, что
// иконки таббара — stroke="currentColor", цвет задаёт CSS.
function MenuIcon({ name }) {
  const props = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    className: "profile-menu-item-icon",
    "aria-hidden": true,
  };
  switch (name) {
    case "offers": // портфель
      return (
        <svg {...props}>
          <rect x="3" y="7.5" width="18" height="12.5" rx="3" />
          <path d="M9.5 7.5V6a1.5 1.5 0 0 1 1.5-1.5h2A1.5 1.5 0 0 1 14.5 6v1.5" />
        </svg>
      );
    case "messages": // облачко реплики
      return (
        <svg {...props}>
          <path d="M20 3.5H4A1.5 1.5 0 0 0 2.5 5v9A1.5 1.5 0 0 0 4 15.5h2.5v4l4.5-4H20a1.5 1.5 0 0 0 1.5-1.5V5A1.5 1.5 0 0 0 20 3.5z" />
        </svg>
      );
    case "rating": // звезда
      return (
        <svg {...props}>
          <path d="M12 3.2l2.7 5.5 6 .9-4.35 4.25 1.03 6-5.38-2.83L6.62 19.85l1.03-6L3.3 9.6l6-.9z" />
        </svg>
      );
    case "qr": // четыре квадрата — мотив QR-метки
      return (
        <svg {...props}>
          <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
          <rect x="14.5" y="4.5" width="5" height="5" rx="1.2" fill="currentColor" stroke="none" />
          <rect x="4.5" y="14.5" width="5" height="5" rx="1.2" fill="currentColor" stroke="none" />
          <rect x="14.5" y="14.5" width="5" height="5" rx="1.2" fill="currentColor" stroke="none" />
        </svg>
      );
    case "cv": // лист документа
      return (
        <svg {...props}>
          <rect x="5" y="3" width="14" height="18" rx="2.5" />
          <path d="M8.5 8.5h7M8.5 12h7M8.5 15.5h4" />
        </svg>
      );
    case "contacts": // человек
      return (
        <svg {...props}>
          <circle cx="12" cy="8" r="3.2" />
          <path d="M5.5 20c.9-3.6 3.4-5.5 6.5-5.5s5.6 1.9 6.5 5.5" />
        </svg>
      );
    case "edit": // карандаш
      return (
        <svg {...props}>
          <path d="M4 20h4l10-10a2.8 2.8 0 0 0-4-4L4 16v4Z" />
          <path d="M13.5 6.5l4 4" />
        </svg>
      );
    case "privacy": // замок — в макете этого пункта нет, см. комментарий к MENU
      return (
        <svg {...props}>
          <rect x="4.5" y="10" width="15" height="10" rx="2.5" />
          <path d="M8.5 10V7a3.5 3.5 0 0 1 7 0v3" />
        </svg>
      );
    default:
      return null;
  }
}

// Порядок пунктов — по макету владельца ("рейтинг порядок.pdf", 16.08.2026):
// Офферы, Сообщения, Рейтинг, QR, CV, Контакты.
const MENU = [
  // 09.09.2026, просьба владельца: правка анкеты прямо в приложении. Стоит
  // первым — остальной порядок задан макетом владельца, его не трогаем.
  { key: "edit", labelKey: "hub.menu.edit" },
  { key: "offers", labelKey: "hub.menu.offers" },
  { key: "messages", labelKey: "hub.menu.messages" },
  { key: "rating", labelKey: "hub.menu.rating" },
  { key: "qr", labelKey: "hub.menu.qr" },
  { key: "cv", labelKey: "hub.menu.cv" },
  { key: "contacts", labelKey: "hub.menu.contacts" },
  // "Приватность" (28.08.2026, макет "09 · Приватность", Untitled-12) —
  // добавлена ПОСЛЕДНЕЙ, за явно заданным владельцем порядком остальных
  // 6 пунктов ("рейтинг порядок.pdf") — этот макет её порядок не задавал.
  { key: "privacy", labelKey: "profile.privacy.menuLabel" },
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
            {profile.company && (
              <div className="profile-header-sub profile-header-sub--muted">{profile.company}</div>
            )}
          </div>
        </div>
        {(profile.vertical || profile.days_in_community != null) && (
          <div className="profile-meta-row">
            {profile.vertical && <span className="profile-vertical-badge">{profile.vertical}</span>}
            {profile.days_in_community != null && (
              <span className="profile-tenure-badge">
                {t("hub.daysInCommunity", {
                  count: profile.days_in_community,
                  unit: lang === "ru"
                    ? pluralRu(profile.days_in_community, ["день", "дня", "дней"])
                    : profile.days_in_community === 1 ? "day" : "days",
                })}
              </span>
            )}
          </div>
        )}
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
            <IconShare /> <span className="link-underline">{t("hub.addToHome")}</span>
          </button>
        )}
      </div>

      <RatingCard
        reputation={profile.reputation_score}
        tier={profile.reputation_tier}
        partnerships={profile.confirmed_partnerships}
        daysInCommunity={profile.days_in_community}
      />

      <TurnoverCard turnover={profile.turnover} />

      {(profile.confirmed_partnerships ?? 0) === 0 && <FirstStepCard onNavigateTab={onNavigateTab} />}

      {/* Статус трудоустройства (04.09.2026, сверка с Figma) — в макете он
          стоит НИЖЕ карточки "Первый шаг" и лежит прямо на фоне, отдельным
          блоком; раньше был засунут внутрь верхней карточки-визитки. */}
      <div className="work-status-section">
        <label>{t("hub.status")}</label>
        <WorkStatusPicker value={profile.work_status} onChange={onWorkStatusChange} />
      </div>

      <div className="card">
        {MENU.map((m) => (
          <button
            key={m.key}
            type="button"
            className="profile-menu-item"
            onClick={() => onNavigateSub(m.key)}
          >
            <span className="profile-menu-item-main">
              <MenuIcon name={m.key} />
              <span>{t(m.labelKey)}</span>
            </span>
            {/* В макете счётчик непрочитанных прижат вправо к шеврону, а не
                идёт сразу за подписью пункта. */}
            {m.key === "messages" && profile.unread_messages > 0 && (
              <span className="thread-unread-badge">{profile.unread_messages}</span>
            )}
            <span className="profile-menu-item-chevron">›</span>
          </button>
        ))}
      </div>
    </div>
  );
}
