import { useState } from "react";
import { MetricsRow, PartnersList } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { useLang } from "../../i18n.jsx";

// Подсказка "как поднять рейтинг" (11.08.2026, по фидбеку владельца —
// PDF-разбор шаг "У вас низкий рейтинг в индустрии. Как исправить?" не вёл
// никуда, копия ниже — то же объяснение, что он сам продиктовал). Тот же
// expand-паттерн, что "Подробнее" в OnboardingScreen.jsx (onboarding-more-link/
// onboarding-detail), для визуальной согласованности.
function RatingHelp() {
  const { t } = useLang();
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="card">
      <button type="button" className="onboarding-more-link" onClick={() => setExpanded((v) => !v)}>
        {expanded ? t("rating.helpHide") : t("rating.helpToggle")}
      </button>
      {expanded && (
        <div className="onboarding-detail">
          <p>{t("rating.help1")}</p>
          <p>{t("rating.help2")}</p>
          <p>{t("rating.help3")}</p>
        </div>
      )}
    </div>
  );
}

export function RatingSubscreen({ profile, privacy, onPrivacyChange, onBack, onNavigate }) {
  const { t } = useLang();
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>

      {!profile.is_subscribed && (
        <div className="card subscription-gate-note">
          <strong>{t("rating.gateTitle")}</strong>
          <p className="partner-meta">{t("rating.gateText")}</p>
          <button className="btn" style={{ width: "auto", padding: "10px 20px" }} onClick={() => onNavigate?.("subscribe")}>
            {t("rating.subscribeCta")}
          </button>
        </div>
      )}

      <div className="card">
        <h3>{t("rating.title")}</h3>
        <MetricsRow
          reputation={profile.reputation_score}
          partnerships={profile.confirmed_partnerships}
          daysInCommunity={profile.days_in_community}
        />
      </div>
      <RatingHelp />
      <div className="card">
        <h3>{t("rating.partnershipsTitle")}</h3>
        <PartnersList partners={profile.partners} emptyHint={t("rating.emptyOwn")} />
      </div>
      <PrivacyToggles
        privacy={privacy}
        onChange={onPrivacyChange}
        fields={["show_reputation", "show_tenure"]}
        hint={t("rating.privacyHint")}
      />
    </div>
  );
}
