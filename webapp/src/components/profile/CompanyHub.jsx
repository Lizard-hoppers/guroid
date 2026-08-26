import { useEffect, useState } from "react";
import { EditableField, Msg } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import {
  getCompanyAddresses, setCompanyProfileField, setCompanyPrivacyField, submitCompanyAddress,
  requestCompanyVerification,
} from "../../api.js";
import { SubscribeScreen } from "../SubscribeScreen.jsx";
import { useLang } from "../../i18n.jsx";
import { ensureHttpUrl, initialOf } from "../../utils.js";
import { haptic } from "../../telegram.js";

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

// Кабинет "Компания" (Фаза 5, 16-17.08.2026; редизайн 26.08.2026 по ТЗ
// "Компания. каб") — зеркало RecruiterHub.jsx, третий воркспейс поверх
// личного профиля. Компания — бренд-страница работодателя, Рекрутер —
// конкретный человек внутри неё; поля независимые, своя подписка/таблица
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
  { field: "cover_url", labelKey: "company.field.coverUrl", placeholderKey: "company.field.coverUrlPlaceholder" },
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

// "Тип компании" (раздел 5 ТЗ) — множественный выбор + "Другое" свободным
// текстом (логируется отдельно на бэкенде, см. log_company_other_type).
// Тот же справочник, что GC.COMPANY_TYPES — маленький фиксированный список,
// поэтому просто продублирован тут (не заводили отдельный API-эндпоинт под
// 7 строк, тот же принцип, что VERTICALS/WORK_FORMATS в VacanciesScreen.jsx).
const COMPANY_TYPES = [
  "operator_casino", "bookmaker", "cpa_network", "hr_agency",
  "media_buying", "b2b_platform", "investor_fund",
];

function CompanyTypesField({ value, otherValue, onSaved }) {
  const { t } = useLang();
  const [busy, setBusy] = useState(false);
  const [otherDraft, setOtherDraft] = useState(otherValue || "");
  const selected = value ? value.split(",").map((s) => s.trim()).filter(Boolean) : [];

  async function toggle(key) {
    if (busy) return;
    const next = selected.includes(key) ? selected.filter((x) => x !== key) : [...selected, key];
    setBusy(true);
    try {
      const updated = await setCompanyProfileField("company_types", next.join(","));
      onSaved("company_types", updated.company_types);
      haptic("select");
    } catch {
      haptic("error");
    } finally {
      setBusy(false);
    }
  }

  async function saveOther() {
    if ((otherDraft || "").trim() === (otherValue || "")) return;
    setBusy(true);
    try {
      const updated = await setCompanyProfileField("company_type_other", otherDraft.trim());
      onSaved("company_type_other", updated.company_type_other);
      haptic("success");
    } catch {
      haptic("error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>{t("company.types.title")}</h3>
      <p className="partner-meta">{t("company.types.hint")}</p>
      <div className="vertical-chips">
        {COMPANY_TYPES.map((key) => (
          <button
            key={key}
            type="button"
            disabled={busy}
            className={`vertical-chip${selected.includes(key) ? " is-selected" : ""}`}
            onClick={() => toggle(key)}
          >
            {t(`company.types.${key}`)}
          </button>
        ))}
      </div>
      <label style={{ marginTop: 10 }}>{t("company.types.otherLabel")}</label>
      <input
        type="text"
        placeholder={t("company.types.otherPlaceholder")}
        value={otherDraft}
        disabled={busy}
        onChange={(e) => setOtherDraft(e.target.value)}
        onBlur={saveOther}
      />
    </div>
  );
}

// Верификация (раздел 2 ТЗ) — ручной MVP: кнопка только показывает адрес/
// формат письма и фиксирует момент запроса, реальную сверку домена делает
// администратор лично (handlers/admin_guro.py), тут только статус.
function VerificationCard({ verified, requestedAt }) {
  const { t } = useLang();
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await requestCompanyVerification();
      setSent(true);
      haptic("success");
    } catch {
      haptic("error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>{t("company.verify.title")}</h3>
      {verified ? (
        <div className="company-verify-status is-verified">✓ {t("company.verify.verified")}</div>
      ) : (
        <>
          <p className="partner-meta">{t("company.verify.hint")}</p>
          {(requestedAt || sent) && (
            <div className="company-verify-status is-pending">{t("company.verify.pending")}</div>
          )}
          <button type="button" className="btn secondary" style={{ marginTop: 10 }} onClick={submit} disabled={busy}>
            {t("company.verify.submitBtn")}
          </button>
        </>
      )}
    </div>
  );
}

// Настройки за иконкой-шестерёнкой (по аналогии с ТЗ по кабинету Рекрутер,
// раздел 1 ТЗ "Компания. каб") — логотип/обложка не обязательны при
// создании, заполняются тут же, позже.
function SettingsPanel({ data, onFieldSaved, onPrivacyChange }) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" className="settings-gear-btn" onClick={() => setOpen((v) => !v)}>
        ⚙️ {t("company.settingsBtn")} {open ? "︿" : "﹀"}
      </button>
      {open && (
        <>
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
          <CompanyTypesField
            value={data.company_types}
            otherValue={data.company_type_other}
            onSaved={onFieldSaved}
          />
          <PrivacyToggles
            privacy={data.privacy}
            onChange={onPrivacyChange}
            fields={PRIVACY_FIELDS}
            savePrivacyField={setCompanyPrivacyField}
            labels={COMPANY_PRIVACY_LABELS}
            hint={t("company.privacyHint")}
          />
        </>
      )}
    </div>
  );
}

export function CompanyHub({ data, onFieldSaved, onPrivacyChange, onSubscribed, onNavigateTab }) {
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

  const types = data.company_types ? data.company_types.split(",").map((s) => s.trim()).filter(Boolean) : [];
  const hasReputation = typeof data.reputation_score === "number";

  return (
    <div>
      {/* Визитка — визуально ОТЛИЧАЕТСЯ и от личного профиля, и от кабинета
          Рекрутер (раздел 3 ТЗ, "с одного взгляда, не читая текст"):
          полноразмерный баннер + квадратный логотип поверх него + бейдж
          верификации + прямоугольная (не круглая) плашка рейтинга +
          вертикаль крупным шрифтом + теги "Тип компании". */}
      <div className="card company-card">
        <div className="company-cover" style={data.cover_url ? { backgroundImage: `url(${data.cover_url})` } : undefined} />
        <div className="company-header">
          {data.logo_url ? (
            <img className="company-logo" src={data.logo_url} alt="" />
          ) : (
            <div className="company-logo-fallback">{initialOf(data.name)}</div>
          )}
          <div className="profile-header-info">
            <h2>
              {data.name || t("common.noName")}
              {data.verified && <span className="company-verified-badge" title={t("company.verify.verified")}>✓</span>}
            </h2>
          </div>
          <div className="company-rating-badge">
            {hasReputation ? Math.round(data.reputation_score) : t("hub.ratingLocked")}
          </div>
        </div>
        {data.vertical && <div className="company-vertical-big">{data.vertical}</div>}
        {(types.length > 0 || data.company_type_other) && (
          <div className="showcase-stack company-types-chips">
            {types.map((key) => <span key={key} className="chip">{t(`company.types.${key}`)}</span>)}
            {data.company_type_other && <span className="chip">{data.company_type_other}</span>}
          </div>
        )}
      </div>

      <SettingsPanel data={data} onFieldSaved={onFieldSaved} onPrivacyChange={onPrivacyChange} />

      <VerificationCard verified={data.verified} requestedAt={data.verification_requested_at} />

      <div className="card">
        <div className="partner-meta" style={{ marginBottom: 10 }}>
          {t("company.activeVacancies", { n: data.active_vacancies })}
        </div>
        <button type="button" className="btn" onClick={() => onNavigateTab("vacancies")}>
          {t("company.quickPublish")}
        </button>
      </div>

      <CompanyAddressCard />
    </div>
  );
}
