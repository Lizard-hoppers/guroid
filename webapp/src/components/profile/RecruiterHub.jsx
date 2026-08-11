import { EditableField } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { setRecruiterProfileField, setRecruiterPrivacyField } from "../../api.js";
import { SubscribeScreen } from "../SubscribeScreen.jsx";
import { useLang } from "../../i18n.jsx";

// Поля витрины рекрутера (Фаза 3, 12.08.2026) — все редактируются прямо
// тут, в отличие от личного профиля, у них нет анкеты-источника вообще
// (см. guro_constants.RECRUITER_EXTRA_FIELDS).
const FIELD_DEFS = [
  { field: "name", labelKey: "recruiter.field.name", placeholderKey: "recruiter.field.namePlaceholder" },
  { field: "company", labelKey: "recruiter.field.company", placeholderKey: "recruiter.field.companyPlaceholder" },
  { field: "vertical", labelKey: "recruiter.field.vertical", placeholderKey: "recruiter.field.verticalPlaceholder" },
  { field: "profession", labelKey: "recruiter.field.profession", placeholderKey: "recruiter.field.professionPlaceholder" },
  { field: "cv_text", labelKey: "recruiter.field.cv", placeholderKey: "recruiter.field.cvPlaceholder", multiline: true },
  { field: "website", labelKey: "recruiter.field.website", placeholderKey: "recruiter.field.websitePlaceholder" },
  { field: "offering", labelKey: "recruiter.field.offering", placeholderKey: "recruiter.field.offeringPlaceholder", multiline: true },
];

const PRIVACY_FIELDS = [
  "show_name", "show_company", "show_vertical", "show_profession", "show_cv", "show_contacts", "show_offers",
];

// Уточнённые ключи перевода под витрину рекрутера — та же PRIVACY_LABELS
// база личного профиля упоминает LinkedIn/"ищу", которых тут нет.
const RECRUITER_PRIVACY_LABELS = {
  show_name: "recruiter.privacy.name",
  show_company: "recruiter.privacy.company",
  show_vertical: "recruiter.privacy.vertical",
  show_profession: "recruiter.privacy.profession",
  show_cv: "recruiter.privacy.cv",
  show_contacts: "recruiter.privacy.contacts",
  show_offers: "recruiter.privacy.offers",
};

// Кабинет рекрутера — отдельная витрина поверх личного профиля (см. план
// 11.08.2026): общий рейтинг/партнёрства, но своя оплата и свои поля.
// Без активной подписки рекрутера показываем апсейл вместо редактора.
export function RecruiterHub({ data, onFieldSaved, onPrivacyChange, onSubscribed }) {
  const { t } = useLang();

  if (!data.is_recruiter_subscribed) {
    return (
      <div>
        <div className="card">
          <h3>{t("recruiter.title")}</h3>
          <p className="partner-meta">{t("recruiter.upsellText")}</p>
        </div>
        <SubscribeScreen product="recruiter" onSubscribed={onSubscribed} />
      </div>
    );
  }

  return (
    <div>
      <div className="card">
        <h3>{t("recruiter.title")}</h3>
        {FIELD_DEFS.map((f) => (
          <EditableField
            key={f.field}
            field={f.field}
            label={t(f.labelKey)}
            placeholder={t(f.placeholderKey)}
            multiline={f.multiline}
            value={data[f.field]}
            onSaved={(v) => onFieldSaved(f.field, v)}
            saveField={setRecruiterProfileField}
          />
        ))}
      </div>
      <PrivacyToggles
        privacy={data.privacy}
        onChange={onPrivacyChange}
        fields={PRIVACY_FIELDS}
        savePrivacyField={setRecruiterPrivacyField}
        labels={RECRUITER_PRIVACY_LABELS}
        hint={t("recruiter.privacyHint")}
      />
    </div>
  );
}
