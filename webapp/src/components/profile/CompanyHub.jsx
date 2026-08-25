import { useEffect, useState } from "react";
import { EditableField, Msg } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { getCompanyAddresses, setCompanyProfileField, setCompanyPrivacyField, submitCompanyAddress } from "../../api.js";
import { SubscribeScreen } from "../SubscribeScreen.jsx";
import { useLang } from "../../i18n.jsx";
import { ensureHttpUrl, initialOf } from "../../utils.js";

// Верификация крипто-адреса компании (ТЗ 5.5, 25.08.2026) — ручное
// подтверждение модератором (/admin, см. handlers/admin_guro.py), после
// одобрения сделки с хешем, совпадающим по адресу, получают повышенный
// множитель рейтинга (5.4, ×2 вместо ×1.3-1.5). Статусы: pending/approved/rejected.
const NETWORK_LABELS = { tron: "TRON (TRC20)", ethereum: "Ethereum (ERC20)", bsc: "BNB Smart Chain (BEP20)" };

function CompanyAddressCard() {
  const { t } = useLang();
  const [addresses, setAddresses] = useState(null);
  const [network, setNetwork] = useState("tron");
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    getCompanyAddresses().then((r) => setAddresses(r.results)).catch(() => setAddresses([]));
  }, []);

  async function submit(e) {
    e.preventDefault();
    if (!address.trim()) return;
    setBusy(true);
    setError(false);
    try {
      await submitCompanyAddress(network, address.trim());
      setAddress("");
      const r = await getCompanyAddresses();
      setAddresses(r.results);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>{t("company.addressTitle")}</h3>
      <p className="partner-meta">{t("company.addressHint")}</p>
      {addresses && addresses.length > 0 && (
        <div>
          {addresses.map((a) => (
            <div key={a.id} className="partner-meta">
              {NETWORK_LABELS[a.network] || a.network}: <span className="partner-tx-hash-value">{a.address}</span>
              {" — "}{t(`company.addressStatus.${a.status}`)}
            </div>
          ))}
        </div>
      )}
      <form onSubmit={submit}>
        <select value={network} onChange={(e) => setNetwork(e.target.value)}>
          {Object.entries(NETWORK_LABELS).map(([k, label]) => (
            <option key={k} value={k}>{label}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder={t("company.addressPlaceholder")}
          value={address}
          onChange={(e) => setAddress(e.target.value)}
        />
        <button className="btn" type="submit" disabled={busy || !address.trim()}>
          {t("company.addressSubmit")}
        </button>
      </form>
      {error && <Msg type="error">{t("company.addressError")}</Msg>}
    </div>
  );
}

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
      <CompanyAddressCard />
    </div>
  );
}
