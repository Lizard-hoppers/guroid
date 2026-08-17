import { EditableField } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { setCompanyProfileField, setCompanyPrivacyField } from "../../api.js";
import { SubscribeScreen } from "../SubscribeScreen.jsx";
import { useLang } from "../../i18n.jsx";
import { ensureHttpUrl, initialOf } from "../../utils.js";

// Кабинет "Компания" (Фаза 5, 16-17.08.2026) — зеркало RecruiterHub.jsx,
// третий воркспейс поверх личного профиля. Компания — бренд-страница
// работодателя, Рекрутер — конкретный человек внутри неё (см.
// AskUserQuestion от 16.08.2026); поля независимые, своя подписка/таблица
// (guro_company_profiles), та же цена, что у рекрутера (800⭐/7000⭐).
const FIELD_DEFS = [
  { field: "name", labelKey: "company.field.name", placeholderKey: "company.field.namePlaceholder" },
  { field: "vertical", labelKey: "company.field.vertical", placeholderKey: "company.field.verticalPlaceholder" },
  {
    field: "website", labelKey: "company.field.website", placeholderKey: "company.field.websitePlaceholder",
    renderValue: (v) => (
      <a href={ensureHttpUrl(v)} target="_blank" rel="noopener noreferrer">{v}</a>
    ),
  },
  { field: "description", labelKey: "company.field.description", placeholderKey: "company.field.descriptionPlaceholder", multiline: true },
  { field: "logo_url", labelKey: "company.field.logoUrl", placeholderKey: "company.field.logoUrlPlaceholder" },
];

const PRIVACY_FIELDS = ["show_name", "show_vertical", "show_cv", "show_contacts"];

// show_cv/show_contacts переиспользованы под description/website — та же
// база PRIVACY_FIELDS у всех трёх кабинетов (см. _COMPANY_PRIVACY_FIELD_MAP
// в guro_id_api.py), но подписи должны говорить про компанию, не CV/связи.
const COMPANY_PRIVACY_LABELS = {
  show_name: "company.privacy.name",
  show_vertical: "company.privacy.vertical",
  show_cv: "company.privacy.description",
  show_contacts: "company.privacy.website",
};

export function CompanyHub({ data, onFieldSaved, onPrivacyChange, onSubscribed }) {
  const { t } = useLang();

  if (!data.is_company_subscribed) {
    return (
      <div>
        <div className="card">
          <h3>{t("company.title")}</h3>
          <p className="partner-meta">{t("company.upsellText")}</p>
        </div>
        <SubscribeScreen product="company" onSubscribed={onSubscribed} />
      </div>
    );
  }

  return (
    <div>
      <div className="card">
        <div className="profile-header-card">
          {data.logo_url ? (
            <img className="profile-avatar" src={data.logo_url} alt="" />
          ) : (
            <div className="profile-avatar-fallback">{initialOf(data.name)}</div>
          )}
          <div className="profile-header-info">
            <h2>{data.name || t("common.noName")}</h2>
          </div>
        </div>
        {data.vertical && <span className="profile-vertical-badge">{data.vertical}</span>}
      </div>

      <div className="card">
        <h3>{t("company.title")}</h3>
        {FIELD_DEFS.map((f) => (
          <EditableField
            key={f.field}
            field={f.field}
            label={t(f.labelKey)}
            placeholder={t(f.placeholderKey)}
            multiline={f.multiline}
            value={data[f.field]}
            onSaved={(v) => onFieldSaved(f.field, v)}
            saveField={setCompanyProfileField}
            renderValue={f.renderValue}
          />
        ))}
      </div>
      <PrivacyToggles
        privacy={data.privacy}
        onChange={onPrivacyChange}
        fields={PRIVACY_FIELDS}
        savePrivacyField={setCompanyPrivacyField}
        labels={COMPANY_PRIVACY_LABELS}
        hint={t("company.privacyHint")}
      />
    </div>
  );
}
