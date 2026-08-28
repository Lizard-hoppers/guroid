import { useEffect, useRef, useState } from "react";
import { EditableField, Msg } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import {
  getCompanyAddresses, setCompanyProfileField, setCompanyPrivacyField, submitCompanyAddress,
  requestCompanyVerification, createCompany, uploadCompanyImage, ApiError,
} from "../../api.js";
import { SubscribeScreen } from "../SubscribeScreen.jsx";
import { useLang } from "../../i18n.jsx";
import { ensureHttpUrl, initialOf } from "../../utils.js";
import { haptic } from "../../telegram.js";

// Загрузка лого/обложки из галереи (28.08.2026, фидбек владельца: раньше
// только вставка готовой ссылки) — реальный файл, POST /api/company/image
// (multipart), бэкенд сам сохраняет и возвращает обновлённые company-поля.
// Обёрнутый children кликабелен целиком (и пустое состояние "+", и уже
// загруженная картинка — заменить тоже можно тапом), input[type=file]
// спрятан рядом. Подсказка про формат/размер — ОТДЕЛЬНЫМ текстом под
// зоной загрузки (сама зона тесная, надпись внутри неё нечитаема).
function ImageUploadArea({ kind, className, hintKey, onUploaded, onError, children, wrap = true }) {
  const { t } = useLang();
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function onFileChange(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const extra = await uploadCompanyImage(kind, file);
      onUploaded(extra);
      haptic("success");
    } catch (err) {
      const code = err instanceof ApiError ? err.code : null;
      const message =
        code === "FILE_TOO_LARGE" ? t("company.upload.tooLarge") :
        code === "UNSUPPORTED_FORMAT" ? t("company.upload.unsupported") :
        t("company.upload.error");
      if (onError) onError(message);
      else setError(message);
      haptic("error");
    } finally {
      setBusy(false);
    }
  }

  const trigger = (
    <>
      <div
        className={`${className}${busy ? " is-uploading" : ""}`}
        onClick={() => !busy && inputRef.current?.click()}
      >
        {children}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        style={{ display: "none" }}
        onChange={onFileChange}
      />
    </>
  );

  if (!wrap) return trigger;
  return (
    <div>
      {trigger}
      {hintKey && <p className="partner-meta company-upload-hint">{t(hintKey)}</p>}
      {error && <Msg type="error">{error}</Msg>}
    </div>
  );
}

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

// Панель "Характеристика" (27.08.2026, ТЗ "экраны по ТЗ от 23.08") — 2×2
// плитки вместо старой строки текста, зеркало RecruiterHub.CharacteristicPanel
// (та же CSS-сетка recruiter-metrics-grid — общестилевая, не завязана на
// конкретный кабинет), но с "Участников команды" вместо "стажа в роли".
function CharacteristicPanel({ data }) {
  const { t } = useLang();
  return (
    <div className="card">
      <h3>{t("company.characteristic.title")}</h3>
      <div className="recruiter-metrics-grid">
        <div className="recruiter-metric">
          <div className="recruiter-metric-value">{data.successful_hires}</div>
          <div className="recruiter-metric-label">{t("company.characteristic.hires")}</div>
        </div>
        <div className="recruiter-metric">
          <div className="recruiter-metric-value">{data.active_vacancies}</div>
          <div className="recruiter-metric-label">{t("company.characteristic.vacancies")}</div>
        </div>
        <div className="recruiter-metric">
          <div className="recruiter-metric-value">{data.responses_7d}</div>
          <div className="recruiter-metric-label">{t("company.characteristic.responses")}</div>
        </div>
        <div className="recruiter-metric">
          <div className="recruiter-metric-value">{data.member_count} / {data.member_limit}</div>
          <div className="recruiter-metric-label">{t("company.characteristic.members")}</div>
        </div>
      </div>
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

// Раздел 1 ТЗ "Роли и управление командой" (27.08.2026) — явное создание
// компании: основатель сразу становится Владельцем (см. handle_create_
// company/get_or_create_company_profile). similar_companies (раздел 1.2) —
// мягкое предупреждение о похожем названии, показывается ПОСЛЕ создания
// (не блокирует), т.к. ответ приходит вместе с готовой компанией.
function CreateCompanyCard({ onCreated }) {
  const { t } = useLang();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [similar, setSimilar] = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const summary = await createCompany({ name: name.trim() });
      if (summary.similar_companies?.length > 0) {
        setSimilar(summary.similar_companies.map((c) => c.name));
      }
      haptic("success");
      onCreated(summary);
    } catch {
      haptic("error");
      setError(t("company.create.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>{t("company.create.title")}</h3>
      <p className="partner-meta">{t("company.create.hint")}</p>
      <form onSubmit={submit}>
        <label>{t("company.create.nameLabel")}</label>
        <input
          type="text"
          placeholder={t("company.create.namePlaceholder")}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button className="btn" type="submit" disabled={busy || !name.trim()} style={{ marginTop: 10 }}>
          {busy ? t("company.create.submitting") : t("company.create.submit")}
        </button>
      </form>
      {similar && (
        <div className="mismatch-banner" style={{ marginTop: 10 }}>
          {t("company.create.similarWarning", { names: similar.join(", ") })}
        </div>
      )}
      <Msg type="error">{error}</Msg>
      <p className="partner-meta" style={{ marginTop: 14 }}>{t("company.create.joinHint")}</p>
    </div>
  );
}

export function CompanyHub({ data, onFieldSaved, onPrivacyChange, onSubscribed, onNavigateTab, onNavigateSub, onCreated }) {
  const { t } = useLang();
  // Тир выбирается ДО первой оплаты (27.08.2026, ТЗ "Тарифы и лимиты") —
  // Basic/Pro это два РАЗНЫХ product (см. SubscribeScreen.jsx), тут просто
  // переключатель, какой из двух показать. После подписки тир уже
  // зафиксирован на бэкенде (data.company_tier) — переключатель прячется.
  const [tierChoice, setTierChoice] = useState("basic");
  // Ошибки/подсказки загрузки лого и обложки выведены из ImageUploadArea
  // (обложка выше .company-header с его margin-top:-30px — если оставить
  // подсказку МЕЖДУ ними, шапка наедет и перекроет текст; лого вообще
  // внутри flex-строки с именем/рейтингом) и показываются ПОСЛЕ визитки
  // целиком, одним блоком на оба поля.
  const [logoUploadError, setLogoUploadError] = useState(null);
  const [coverUploadError, setCoverUploadError] = useState(null);

  // no_company (27.08.2026, ТЗ "Роли и управление командой") — юзер не
  // Владелец и не Админ ни в одной компании: либо создаёт свою, либо
  // находит чужую (доска вакансий/поиск) и подаёт заявку с её карточки.
  if (data.no_company) {
    return <CreateCompanyCard onCreated={onCreated} />;
  }

  if (!data.is_company_subscribed) {
    return (
      <div>
        <div className="card">
          <h3>{t("company.title")}</h3>
          <p className="partner-meta">{t("company.upsellText")}</p>
          <div className="vertical-chips" style={{ marginTop: 10 }}>
            <button
              type="button"
              className={`vertical-chip${tierChoice === "basic" ? " is-selected" : ""}`}
              onClick={() => setTierChoice("basic")}
            >
              {t("company.tier.basic")}
            </button>
            <button
              type="button"
              className={`vertical-chip${tierChoice === "pro" ? " is-selected" : ""}`}
              onClick={() => setTierChoice("pro")}
            >
              {t("company.tier.pro")}
            </button>
          </div>
          <p className="partner-meta" style={{ marginTop: 8 }}>
            {tierChoice === "pro" ? t("company.tier.proHint") : t("company.tier.basicHint")}
          </p>
        </div>
        <SubscribeScreen product={tierChoice === "pro" ? "company_pro" : "company_basic"} onSubscribed={onSubscribed} />
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
        <ImageUploadArea
          kind="cover"
          className="company-cover"
          wrap={false}
          onUploaded={(extra) => onFieldSaved("cover_url", extra.cover_url)}
          onError={setCoverUploadError}
        >
          {data.cover_url ? (
            <div className="company-cover-filled" style={{ backgroundImage: `url(${data.cover_url})` }} />
          ) : (
            <div className="company-cover-empty">+ {t("company.upload.coverBtn")}</div>
          )}
        </ImageUploadArea>
        <div className="company-header">
          <ImageUploadArea
            kind="logo"
            className="company-logo-upload"
            wrap={false}
            onUploaded={(extra) => onFieldSaved("logo_url", extra.logo_url)}
            onError={setLogoUploadError}
          >
            {data.logo_url ? (
              <img className="company-logo" src={data.logo_url} alt="" />
            ) : (
              <div className="company-logo-fallback">{initialOf(data.name)}</div>
            )}
          </ImageUploadArea>
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
        <span className="recruiter-role-badge">{t(`company.tier.${data.company_tier || "basic"}`)}</span>
        {/* Роль в компании (27.08.2026, ТЗ "Роли и управление командой") —
            Владелец/Админ, НЕ должность по жизни (та отдельным текстом). */}
        <span className="recruiter-role-badge" style={{ marginLeft: 6 }}>{t(`team.role.${data.my_role}`)}</span>
        {data.my_position && <div className="partner-meta" style={{ marginTop: 4 }}>{data.my_position}</div>}
        {data.vertical && <div className="company-vertical-big">{data.vertical}</div>}
        {(types.length > 0 || data.company_type_other) && (
          <div className="showcase-stack company-types-chips">
            {types.map((key) => <span key={key} className="chip">{t(`company.types.${key}`)}</span>)}
            {data.company_type_other && <span className="chip">{data.company_type_other}</span>}
          </div>
        )}
      </div>
      <p className="partner-meta company-upload-hint">{t("company.upload.coverHint")}</p>
      <p className="partner-meta company-upload-hint">{t("company.upload.logoHint")}</p>
      {coverUploadError && <Msg type="error">{coverUploadError}</Msg>}
      {logoUploadError && <Msg type="error">{logoUploadError}</Msg>}

      <SettingsPanel data={data} onFieldSaved={onFieldSaved} onPrivacyChange={onPrivacyChange} />

      <CharacteristicPanel data={data} />

      <div className="card recruiter-quick-actions is-stacked">
        <button type="button" className="btn" onClick={() => onNavigateTab("vacancies")}>
          {t("company.quickPublish")}
        </button>
        <button type="button" className="btn secondary" onClick={() => onNavigateSub("company-candidates")}>
          {t("company.quickFind")}
        </button>
        <button type="button" className="btn secondary" onClick={() => onNavigateSub("company-team")}>
          {t("team.title")} · {t("team.counter", { count: data.member_count, limit: data.member_limit })}
        </button>
      </div>

      <VerificationCard verified={data.verified} requestedAt={data.verification_requested_at} />

      <CompanyAddressCard />

      <div className="card">
        <button type="button" className="profile-menu-item" onClick={() => onNavigateSub("tariffs")}>
          <span>{t("company.menu.tariffs")}</span>
          <span className="profile-menu-item-chevron">›</span>
        </button>
      </div>
    </div>
  );
}
