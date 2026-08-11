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
        <label>{t("offers.lookingForLabel")}</label>
        {profile.looking_for ? (
          <div className="editable-field-value">{profile.looking_for}</div>
        ) : (
          <div className="editable-field-empty">{t("offers.lookingForEmpty")}</div>
        )}
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
