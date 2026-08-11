import { useState } from "react";
import { openTelegramLink } from "../../telegram.js";
import { useLang, ONBOARDING_VERTICALS } from "../../i18n.jsx";

// Экран первого запуска (нет анкеты -> нет профиля GURO ID) — по ручному
// эскизу заказчика: макет ID-карты с плейсхолдерами, короткое объяснение,
// раскрывающееся "Подробнее" с полным питчем + ценами, CTA на анкету бота.
export function OnboardingScreen() {
  const { t, lang } = useLang();
  const [expanded, setExpanded] = useState(false);
  const verticals = ONBOARDING_VERTICALS[lang] || ONBOARDING_VERTICALS.ru;

  return (
    <div>
      <div className="card">
        <div className="profile-header-card onboarding-mock-card">
          <div className="profile-avatar-fallback onboarding-mock-avatar">🏃</div>
          <div className="profile-header-info">
            <h2 className="onboarding-mock-placeholder">Name?</h2>
            <div className="profile-header-sub onboarding-mock-placeholder">Position?</div>
            <div className="profile-header-sub onboarding-mock-placeholder">Company?</div>
          </div>
        </div>

        <h3 style={{ marginTop: 16 }}>{t("onboarding.title")}</h3>
        <p className="partner-meta">
          {t("onboarding.intro")}{" "}
          <button type="button" className="onboarding-more-link" onClick={() => setExpanded((v) => !v)}>
            {t("onboarding.more")}
          </button>
        </p>

        {expanded && (
          <div className="onboarding-detail">
            <p>{t("onboarding.detail1")}</p>
            <ul className="onboarding-verticals">
              {verticals.map((v) => (
                <li key={v}>{v}</li>
              ))}
            </ul>
            <p>{t("onboarding.detail2")}</p>
            <p>{t("onboarding.detail3")}</p>
            <p>{t("onboarding.detail4")}</p>
            <p>{t("onboarding.priceLine", { monthly: "$10", yearly: "$99" })}</p>
          </div>
        )}
      </div>

      <div className="card">
        <p className="partner-meta">{t("onboarding.ctaHint")}</p>
        <button className="btn" onClick={() => openTelegramLink("https://t.me/GamblingCommunitybot")}>
          {t("onboarding.ctaBtn")}
        </button>
      </div>
    </div>
  );
}
