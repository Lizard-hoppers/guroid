import { EditableField } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { setRecruiterProfileField, setRecruiterPrivacyField } from "../../api.js";
import { SubscribeScreen } from "../SubscribeScreen.jsx";
import { useLang } from "../../i18n.jsx";
import { ensureHttpUrl, initialOf } from "../../utils.js";

// Поля витрины рекрутера (Фаза 3, 12.08.2026) — все редактируются прямо
// тут, в отличие от личного профиля, у них нет анкеты-источника вообще
// (см. guro_constants.RECRUITER_EXTRA_FIELDS). logo_url добавлен
// 16.08.2026 (фидбек владельца — "нету возможности загрузить логотип") —
// ссылка на картинку, не файловая загрузка: у guro_id_api нет ни
// multipart-приёма, ни файлового хранилища/CDN, заводить их ради одной
// картинки — избыточно, а ссылка решает ту же задачу мгновенно.
const FIELD_DEFS = [
  { field: "name", labelKey: "recruiter.field.name", placeholderKey: "recruiter.field.namePlaceholder" },
  { field: "company", labelKey: "recruiter.field.company", placeholderKey: "recruiter.field.companyPlaceholder" },
  { field: "vertical", labelKey: "recruiter.field.vertical", placeholderKey: "recruiter.field.verticalPlaceholder" },
  { field: "profession", labelKey: "recruiter.field.profession", placeholderKey: "recruiter.field.professionPlaceholder" },
  { field: "cv_text", labelKey: "recruiter.field.cv", placeholderKey: "recruiter.field.cvPlaceholder", multiline: true },
  {
    field: "website", labelKey: "recruiter.field.website", placeholderKey: "recruiter.field.websitePlaceholder",
    renderValue: (v) => (
      <a href={ensureHttpUrl(v)} target="_blank" rel="noopener noreferrer">{v}</a>
    ),
  },
  { field: "offering", labelKey: "recruiter.field.offering", placeholderKey: "recruiter.field.offeringPlaceholder", multiline: true },
  { field: "logo_url", labelKey: "recruiter.field.logoUrl", placeholderKey: "recruiter.field.logoUrlPlaceholder" },
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
      {/* Карточка-визитка (16.08.2026, фидбек владельца — "нету карточки
          как в личном профиле") — та же разметка/классы, что у ProfileHub,
          для визуальной согласованности. Логотип вместо аватара из
          Telegram (у витрины рекрутера нет привязки к аккаунту Telegram
          для фото — только то, что владелец сам впишет в logo_url). */}
      <div className="card">
        <div className="profile-header-card">
          {data.logo_url ? (
            <img className="profile-avatar" src={data.logo_url} alt="" />
          ) : (
            <div className="profile-avatar-fallback">{initialOf(data.name, data.company)}</div>
          )}
          <div className="profile-header-info">
            <h2>{data.name || t("common.noName")}</h2>
            {data.profession && <div className="profile-header-sub">{data.profession}</div>}
            {data.company && <div className="profile-header-sub">{data.company}</div>}
          </div>
        </div>
        {data.vertical && <span className="profile-vertical-badge">{data.vertical}</span>}
      </div>

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
            renderValue={f.renderValue}
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
