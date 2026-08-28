import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { useLang } from "../../i18n.jsx";

// "Приватность профиля" (28.08.2026, макет "09 · Приватность",
// Untitled-12) — тумблеры show_name/show_company/show_vertical/
// show_profession раньше жили прямо на главном экране Профиля
// (ProfileHub.jsx), их убрали оттуда по фидбеку владельца ("01 ·
// Профиль (личный)"), но не совсем — макет "09" показал, что они
// переехали на СВОЙ отдельный экран, а не исчезли вовсе. opt-out
// (по умолчанию видно, можно скрыть) — см. guro_id_api.py::
// _PRIVACY_FIELD_MAP.
export function PrivacySubscreen({ privacy, onPrivacyChange, onBack }) {
  const { t } = useLang();
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <PrivacyToggles
        privacy={privacy}
        onChange={onPrivacyChange}
        fields={["show_name", "show_company", "show_vertical", "show_profession"]}
        hint={t("profile.privacy.hint")}
        title={t("profile.privacy.title")}
      >
        <div className="profile-privacy-locked-note">
          <div className="profile-privacy-locked-title">{t("profile.privacy.lockedTitle")}</div>
          <div className="partner-meta">{t("profile.privacy.lockedText")}</div>
        </div>
      </PrivacyToggles>
    </div>
  );
}
