import { EditableField } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { useLang } from "../../i18n.jsx";

export function OffersSubscreen({ profile, privacy, onPrivacyChange, onFieldSaved, onBack }) {
  const { t } = useLang();
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <div className="card">
        <h3>{t("offers.title")}</h3>
        <EditableField
          field="looking_for"
          label={t("offers.lookingForLabel")}
          placeholder={t("offers.lookingForPlaceholder")}
          value={profile.looking_for}
          multiline
          onSaved={(v) => onFieldSaved("looking_for", v)}
        />
        <EditableField
          field="offering"
          label={t("offers.offeringLabel")}
          placeholder={t("offers.offeringPlaceholder")}
          value={profile.offering}
          multiline
          onSaved={(v) => onFieldSaved("offering", v)}
        />
      </div>
      <PrivacyToggles
        privacy={privacy}
        onChange={onPrivacyChange}
        fields={["show_offers"]}
        hint={t("offers.privacyHint")}
      />
    </div>
  );
}
