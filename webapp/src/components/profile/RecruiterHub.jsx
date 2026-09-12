import { useEffect, useState } from "react";
import { ActivationPreview, EditableField, ImageUploadArea, Msg, RatingPreview, TurnoverCard, usePersistentReveal } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import {
  setRecruiterProfileField, setRecruiterPrivacyField, setRecruiterActivityStatus, uploadRecruiterImage,
  getPlans,
} from "../../api.js";
import { SubscribeScreen } from "../SubscribeScreen.jsx";
import { useLang } from "../../i18n.jsx";
import { IconBriefcase, IconGear, IconTrophy } from "../Icons.jsx";
import { haptic } from "../../telegram.js";
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
  // logo_url убран из списка полей 06.09.2026 («рекрутер каб.pdf», стр. 1):
  // логотип задаётся тапом по аватару на главном экране, а не ссылкой.
  // Ссылку из поисковой выдачи (редирект на страницу, а не на файл) поле
  // принимало молча, и картинка не появлялась.
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

// Статус активности (2.4, ТЗ "Гуро рекрутер каб") — простой 2-позиционный
// переключатель, повторный тап по активному снимает статус (тот же
// принцип "выкл = null", что у WorkStatusPicker личного профиля, но без
// его анимированной капли — тут всего 2 состояния, усложнять незачем).
function ActivityStatusToggle({ value, onChange }) {
  const { t } = useLang();
  const [saving, setSaving] = useState(false);

  async function pick(next) {
    const value2 = value === next ? null : next;
    setSaving(true);
    haptic("light");
    try {
      const res = await setRecruiterActivityStatus(value2);
      onChange(res.activity_status);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="activity-status-toggle">
      <button
        type="button"
        className={value === "hiring" ? "is-active hiring" : ""}
        disabled={saving}
        onClick={() => pick("hiring")}
      >
        {t("recruiter.activity.hiring")}
      </button>
      <button
        type="button"
        className={value === "not_hiring" ? "is-active not-hiring" : ""}
        disabled={saving}
        onClick={() => pick("not_hiring")}
      >
        {t("recruiter.activity.notHiring")}
      </button>
    </div>
  );
}

// Панель "Характеристика" (2.3) — 4 метрики кабинета рекрутера. Заменяет
// место, которое раньше занимали поля настроек (см. SettingsPanel ниже —
// вынесены под шестерёнку, 2.2).
function CharacteristicPanel({ data }) {
  const { t } = useLang();
  return (
    <div className="card">
      <h3>{t("recruiter.characteristic.title")}</h3>
      <div className="recruiter-metrics-grid">
        <div className="recruiter-metric">
          <div className={`recruiter-metric-value${data.successful_hires === 0 ? " is-neutral" : ""}`}>{data.successful_hires}</div>
          <div className="recruiter-metric-label">{t("recruiter.characteristic.hires")}</div>
        </div>
        <div className="recruiter-metric">
          <div className={`recruiter-metric-value${data.active_vacancies === 0 ? " is-neutral" : ""}`}>{data.active_vacancies}</div>
          <div className="recruiter-metric-label">{t("recruiter.characteristic.vacancies")}</div>
        </div>
        <div className="recruiter-metric">
          <div className={`recruiter-metric-value${data.responses_7d === 0 ? " is-neutral" : ""}`}>{data.responses_7d}</div>
          <div className="recruiter-metric-label">{t("recruiter.characteristic.responses")}</div>
        </div>
        <div className="recruiter-metric">
          {/* Стаж в роли — не "результат", а факт; всегда нейтральный цвет
              (29.08.2026, тот же принцип, что и у CompanyHub). */}
          <div className="recruiter-metric-value is-neutral">{data.tenure_days ?? "—"}</div>
          <div className="recruiter-metric-label">{t("recruiter.characteristic.tenure")}</div>
        </div>
      </div>
    </div>
  );
}

// Блок процентиля (2.5) — читает ТОЛЬКО кэш (percentile_tier/computed_at),
// пересчитывается раз в сутки фоновым джобом
// (guro_recruiter_percentile_sync.py). tier=null покрывает три случая
// разом (0 наймов / ниже топ-50% / вертикаль ещё без 30 рекрутеров-
// сэмпла) — везде показываем один и тот же CTA, отличать их пользователю
// не нужно, действие («подтвердить прошлый найм») одно и то же.
function PercentileBlock({ tier, vertical, onConfirmHire }) {
  const { t } = useLang();
  if (tier) {
    return (
      <div className="card percentile-block percentile-good">
        <div className="percentile-badge">
      <IconTrophy /> {t("recruiter.percentile.top", { tier })}{vertical ? ` ${vertical}` : ""}</div>
        <p className="partner-meta">{t("recruiter.percentile.goodText")}</p>
      </div>
    );
  }
  return (
    <div className="card percentile-block">
      <h3>{t("recruiter.percentile.ctaTitle")}</h3>
      <p className="partner-meta">{t("recruiter.percentile.ctaText")}</p>
      <button type="button" className="btn secondary" onClick={onConfirmHire}>
        {t("recruiter.percentile.ctaButton")}
      </button>
    </div>
  );
}

// Настройки за иконкой-шестерёнкой (2.2) — имя/компания/вертикаль/
// должность/CV/сайт/офферы/лого + приватность, свёрнуты за кнопку, чтобы
// не занимать первый экран (настраиваются один раз, редко меняются).
function SettingsPanel({ data, onFieldSaved, onPrivacyChange }) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  return (
    <div>
      <div className="settings-gear-row">
        <button type="button" className="settings-gear-btn" onClick={() => setOpen((v) => !v)}>
          <IconGear /> {t("recruiter.settingsBtn")}
        </button>
      </div>
      {open && (
        <>
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
            {/* Здесь человек и ищет логотип — значит здесь и надо сказать,
                где он задаётся и какой файл подойдёт («рекрутер каб.pdf»,
                стр. 1: «нужно написать юзеру какие именно размеры»). */}
            <div className="privacy-hint recruiter-logo-note">
              {t("recruiter.logoInSettings")}
            </div>
          </div>
          <PrivacyToggles
            privacy={data.privacy}
            onChange={onPrivacyChange}
            fields={PRIVACY_FIELDS}
            savePrivacyField={setRecruiterPrivacyField}
            labels={RECRUITER_PRIVACY_LABELS}
            hint={t("recruiter.privacyHint")}
          />
        </>
      )}
    </div>
  );
}

// Кабинет рекрутера — отдельная витрина поверх личного профиля (см. план
// 11.08.2026): общий рейтинг/партнёрства, но своя оплата и свои поля.
// Без активной подписки рекрутера показываем апсейл вместо редактора.
//
// 26.08.2026 (ТЗ "Гуро рекрутер каб", главный экран) — полный редизайн
// главного экрана: карточка визуально отличается от личного профиля
// (полоса-обложка + бейдж роли, форма аватара), настройки свёрнуты за
// шестерёнку, добавлены "Характеристика" (4 метрики), статус активности,
// блок процентиля, быстрые действия, блок коммуникации (Сообщения/
// Отклики/Мой QR — Сообщения это ТОТ ЖЕ единый инбокс, что у личного
// профиля, не отдельный ящик, см. onOpenMessages).
export function RecruiterHub({
  data, onFieldSaved, onPrivacyChange, onSubscribed, onNavigateSub, onActivityChange, onNavigateTab,
}) {
  const { t } = useLang();
  const [logoUploadError, setLogoUploadError] = useState(null);
  const [removingLogo, setRemovingLogo] = useState(false);

  // "Удалить фото" (12.09.2026, просьба владельца) — тот же field-setter,
  // что и текстовые поля витрины, просто со значением null. Кнопка живёт
  // рядом с подсказкой про загрузку (та же условная зона: одно вместо
  // другого — до и после того, как фото появилось).
  async function removeLogo() {
    setRemovingLogo(true);
    setLogoUploadError(null);
    try {
      const extra = await setRecruiterProfileField("logo_url", null);
      onFieldSaved("logo_url", extra.logo_url ?? null);
      haptic("success");
    } catch {
      setLogoUploadError(t("common.saveError"));
      haptic("error");
    } finally {
      setRemovingLogo(false);
    }
  }
  // Кнопка карточки-тизера ActivationPreview раскрывает тариф, а не платит
  // сама (11.09.2026) — платёжный выбор (месяц/год, крипта/звёзды) ниже
  // остаётся тем же SubscribeScreen, просто не показан сразу.
  const [showPlans, revealPlansRaw] = usePersistentReveal("guro_reveal_recruiter_plans");
  // Кнопка "не работала" (12.09.2026, репорт владельца) — раскрывала
  // SubscribeScreen за пределами видимой области, без скролла к нему.
  const [plansRef, setPlansRef] = useState(null);
  function revealPlans() {
    revealPlansRaw();
    requestAnimationFrame(() => plansRef?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }
  // Реальная цена из /api/plans вместо статичного текста i18n — курс
  // звёзд в доллары не круглый, "$19/мес" в тексте разошлось с реальной
  // ценой в крипте ($18.75).
  const [monthlyPlan, setMonthlyPlan] = useState(null);
  useEffect(() => {
    getPlans({ product: "recruiter" }).then((d) => setMonthlyPlan(d.plans?.monthly)).catch(() => {});
  }, []);
  const priceValue = monthlyPlan
    ? `$${monthlyPlan.crypto_price_usd}${t("activationRecruiter.priceValue").replace(/^\$[\d.]+/, "")}`
    : t("activationRecruiter.priceValue");

  if (!data.is_recruiter_subscribed) {
    return (
      <div>
        <ActivationPreview
          title={t("activationRecruiter.title")}
          nowAvatar={<IconBriefcase size={22} />}
          nowName={t("activationRecruiter.nowName")}
          nowSub={t("activationRecruiter.nowSub")}
          nowBadge={null}
          aboutText={t("activationRecruiter.about")}
          exampleAvatar={initialOf(t("activationRecruiter.exampleName"))}
          exampleName={t("activationRecruiter.exampleName")}
          exampleSub={t("activationRecruiter.exampleSub")}
          exampleBadge={235}
          stat1Label={t("activationRecruiter.stat1Label")}
          stat1Value="12"
          stat2Label={t("activationRecruiter.stat2Label")}
          stat2Value="27"
          metaLine={t("activationRecruiter.metaLine")}
          lockText={t("activationRecruiter.lockText")}
          priceLabel={t("activationRecruiter.priceLabel")}
          priceValue={priceValue}
          ctaLabel={t("activationRecruiter.cta")}
          onActivate={revealPlans}
        />
        {showPlans && (
          <div ref={setPlansRef}>
            <SubscribeScreen product="recruiter" onSubscribed={onSubscribed} />
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      {/* "Настройки" стоят НАД визиткой (макет "11 · Кабинет Рекрутер"):
          раньше кнопка была под ней и во всю ширину. */}
      <SettingsPanel data={data} onFieldSaved={onFieldSaved} onPrivacyChange={onPrivacyChange} />

      {/* Карточка-визитка — визуально ОТЛИЧАЕТСЯ от личного профиля (2.1):
          полоса-обложка сверху с подписью режима + аватар-сквиркл с
          бирюзовой рамкой + бейдж "HR" на аватаре. Приведено в соответствие
          с макетом "11 · Рекрутер — главный экран" (28.08.2026) — раньше
          был приблизительный вариант ("референс-скетч владельца не был
          приложен файлом", см. git-историю), теперь есть готовый макет. */}
      <div className="card recruiter-card">
        <div className="recruiter-card-cover">
          <span className="recruiter-mode-label">{t("recruiter.modeLabel")}</span>
        </div>
        <div className="profile-header-card recruiter-header">
          {/* Аватар кликабелен целиком — тап открывает галерею, тем же
              компонентом, что логотип компании (05.09.2026, просьба
              владельца). Заменить уже загруженный тоже можно тапом. */}
          <ImageUploadArea
            upload={uploadRecruiterImage}
            className="recruiter-avatar-upload"
            wrap={false}
            onUploaded={(extra) => onFieldSaved("logo_url", extra.logo_url)}
            onError={setLogoUploadError}
          >
            {data.logo_url ? (
              <img className="profile-avatar recruiter-avatar" src={data.logo_url} alt="" />
            ) : (
              <div className="profile-avatar-fallback recruiter-avatar">{initialOf(data.name, data.company)}</div>
            )}
          </ImageUploadArea>
          <span className="recruiter-role-badge">{t("recruiter.roleBadge")}</span>
          <div className="profile-header-info">
            <h2>{data.name || t("common.noName")}</h2>
            {(data.profession || data.company) && (
              <div className="profile-header-sub">
                {[data.profession, data.company].filter(Boolean).join(" · ")}
              </div>
            )}
            {data.vertical && <div className="recruiter-vertical-line">{data.vertical}</div>}
          </div>
          <RatingPreview reputation={data.reputation_score} onOpen={() => onNavigateSub("recruiter-history")} />
        </div>
      </div>
      {/* То же правило, что в кабинете компании: подсказка исчезает, когда
          логотип уже загружен. */}
      {!data.logo_url && (
        <p className="partner-meta company-upload-hint">{t("recruiter.upload.logoHint")}</p>
      )}
      {data.logo_url && (
        <button
          type="button"
          className="rate-inline-link rate-inline-link--danger"
          disabled={removingLogo}
          onClick={removeLogo}
        >
          {t("photo.removeLogo")}
        </button>
      )}
      {logoUploadError && <Msg type="error">{logoUploadError}</Msg>}

      <CharacteristicPanel data={data} />
      <TurnoverCard turnover={data.turnover} />

      <div className="card">
        <h3>{t("recruiter.activity.label")}</h3>
        <ActivityStatusToggle value={data.activity_status} onChange={onActivityChange} />
      </div>

      <PercentileBlock
        tier={data.percentile_tier}
        vertical={data.vertical}
        onConfirmHire={() => onNavigateSub("recruiter-confirm")}
      />

      <div className="card recruiter-quick-actions is-stacked">
        <h3>{t("recruiter.quickActions.title")}</h3>
        <button type="button" className="btn" onClick={() => onNavigateTab("vacancies")}>
          {t("recruiter.quickPublish")}
        </button>
        <button type="button" className="btn secondary" onClick={() => onNavigateSub("recruiter-candidates")}>
          {t("recruiter.quickFind")}
        </button>
      </div>

      <div className="card recruiter-menu">
        <h3>{t("recruiter.communication.title")}</h3>
        {[
          { key: "messages", labelKey: "recruiter.menu.messages" },
          { key: "recruiter-responses", labelKey: "recruiter.menu.responses" },
          { key: "recruiter-qr", labelKey: "recruiter.menu.qr" },
        ].map((m) => (
          <button key={m.key} type="button" className="profile-menu-item" onClick={() => onNavigateSub(m.key)}>
            <span>{t(m.labelKey)}</span>
            <span className="profile-menu-item-chevron">›</span>
          </button>
        ))}
      </div>
    </div>
  );
}
