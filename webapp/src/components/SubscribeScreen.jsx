import { useEffect, useState } from "react";
import { getMe, getPlans, subscribe, subscribeCrypto } from "../api.js";
import { Msg } from "./Shared.jsx";
import { openInvoice, openTelegramLink, haptic } from "../telegram.js";
import { formatDate, pluralRu } from "../utils.js";
import { useLang } from "../i18n.jsx";
import { IconCheck, IconStar } from "./Icons.jsx";

const COMPARE_ROWS = [
  "subscribe.compare.workStatus",
  "subscribe.compare.rating",
  "subscribe.compare.search",
  "subscribe.compare.history",
];

// "Что даёт подписка" (28.08.2026, макет "10 · Подписка", Untitled-13) —
// простой чек-лист вместо таблицы бесплатно/платно, только для product
// "guro_id" (единственный, для которого есть этот макет — recruiter/
// company пока используют старый COMPARE_ROWS до своей сверки).
const GURO_BENEFITS = [
  "subscribe.benefit.privacy",
  "subscribe.benefit.partnerships",
  "subscribe.benefit.search",
  "subscribe.benefit.priority",
];

function daysUntil(dbDateString) {
  if (!dbDateString) return null;
  const then = new Date(dbDateString.replace(" ", "T") + "Z").getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.ceil((then - Date.now()) / 86400000));
}

// Кабинет рекрутера (Фаза 3, 12.08.2026) — та же оплата Stars+крипто, что у
// базовой подписки, параметризована по product вместо копии экрана.
const RECRUITER_COMPARE_ROWS = [
  "subscribe.compareRecruiter.rating",
  "subscribe.compareRecruiter.showcase",
  "subscribe.compareRecruiter.visibility",
];

// Чек-листы "что даёт подписка" для кабинетов (05.09.2026, просьба
// владельца — привести к формату базовой подписки). Наличие benefits
// заодно включает продление: см. showRenewal ниже.
const RECRUITER_BENEFITS = [
  "subscribe.benefitRecruiter.showcase",
  "subscribe.benefitRecruiter.vacancies",
  "subscribe.benefitRecruiter.candidates",
  "subscribe.benefitRecruiter.hire",
];

const COMPANY_BASIC_BENEFITS = [
  "subscribe.benefitCompany.brand",
  "subscribe.benefitCompany.recruiter",
  "subscribe.benefitCompany.teamBasic",
];

const COMPANY_PRO_BENEFITS = [
  "subscribe.benefitCompany.brand",
  "subscribe.benefitCompany.recruiter",
  "subscribe.benefitCompany.teamPro",
  "subscribe.benefitCompany.limitsPro",
];

// Кабинет "Компания" (Фаза 5, 16-17.08.2026) — та же цепочка, третий product.
const COMPANY_COMPARE_ROWS = [
  "subscribe.compareCompany.brand",
  "subscribe.compareCompany.showcase",
  "subscribe.compareCompany.visibility",
];

// Тир строки в COMPARE_ROWS вычисляется по позиции — первая всегда
// бесплатная (статус трудоустройства / общий рейтинг), остальные платные.
// Не идеально общее решение, но проще, чем городить отдельный объект ради
// одного булева флага на 3-4 строки. У кабинета компании бесплатной строки
// нет вообще (freeIndex остаётся -1 через ?? ниже).
const FREE_ROW_INDEX = { guro_id: 0, recruiter: 0 };

// Конфиг по product — вместо растущего дерева isRecruiter/isCompany
// тернарников (см. фидбек-урок сессии: параметризация вместо копий экрана).
const PRODUCT_CONFIG = {
  guro_id: {
    workspace: undefined,
    subscribedKey: "is_subscribed",
    expiresKey: "subscription_expires_at",
    cycleKey: "subscription_cycle_days",
    titleKey: "subscribe.titleGuro",
    hintKey: "subscribe.hintGuro",
    compareRows: COMPARE_ROWS,
    benefits: GURO_BENEFITS,
  },
  recruiter: {
    workspace: "recruiter",
    subscribedKey: "is_recruiter_subscribed",
    expiresKey: "recruiter_subscription_expires_at",
    titleKey: "subscribe.titleRecruiter",
    hintKey: "subscribe.hintRecruiter",
    compareRows: RECRUITER_COMPARE_ROWS,
    benefits: RECRUITER_BENEFITS,
  },
  // company_basic/company_pro (27.08.2026, ТЗ "Тарифы и лимиты") — ДВА тира
  // одного кабинета "Компания", каждый свой "product" (см. _PRODUCT_PLANS в
  // guro_id_api.py) — просто разные цены/лимиты, витрина и is_company_subscribed
  // те же самые (см. CompanyHub.jsx — тир выбирается ДО первой оплаты).
  company_basic: {
    workspace: "company",
    subscribedKey: "is_company_subscribed",
    expiresKey: "company_subscription_expires_at",
    titleKey: "subscribe.titleCompanyBasic",
    hintKey: "subscribe.hintCompanyBasic",
    compareRows: COMPANY_COMPARE_ROWS,
    benefits: COMPANY_BASIC_BENEFITS,
  },
  company_pro: {
    workspace: "company",
    subscribedKey: "is_company_subscribed",
    expiresKey: "company_subscription_expires_at",
    titleKey: "subscribe.titleCompanyPro",
    hintKey: "subscribe.hintCompanyPro",
    compareRows: COMPANY_COMPARE_ROWS,
    benefits: COMPANY_PRO_BENEFITS,
  },
};

// me/plans — необязательные: если их передали сверху (см.
// SubscriptionsScreen, где на экране сразу несколько блоков), компонент
// сеть не трогает вовсе. Без них грузит себя сам — так его рендерят
// кабинеты Рекрутер и Компания, где блок на экране один.
export function SubscribeScreen({ product = "guro_id", onSubscribed, me: meProp, plans: plansProp }) {
  const { t, lang } = useLang();
  const cfg = PRODUCT_CONFIG[product] ?? PRODUCT_CONFIG.guro_id;
  const [meSelf, setMeSelf] = useState(null);
  const [plansSelf, setPlansSelf] = useState(null);
  const me = meProp !== undefined ? meProp : meSelf;
  const plansData = plansProp !== undefined ? plansProp : plansSelf;
  const [selected, setSelected] = useState("monthly");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [justPaid, setJustPaid] = useState(false);

  useEffect(() => {
    if (meProp !== undefined) return; // статус пришёл сверху
    getMe({ workspace: cfg.workspace })
      .then(setMeSelf)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [justPaid, meProp]);

  useEffect(() => {
    if (plansProp !== undefined) return; // тарифы пришли сверху
    getPlans({ product })
      .then(setPlansSelf)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [product, plansProp]);

  useEffect(() => {
    if (justPaid) onSubscribed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [justPaid]);

  async function onSubscribeStars() {
    setBusy(true);
    setError("");
    try {
      const { invoice_link } = await subscribe(selected, { product });
      openInvoice(invoice_link, (status) => {
        setBusy(false);
        if (status === "paid") {
          setJustPaid(true);
          haptic("success");
        }
      });
    } catch {
      setBusy(false);
      setError(t("subscribe.starsError"));
      haptic("error");
    }
  }

  async function onSubscribeCrypto() {
    setBusy(true);
    setError("");
    try {
      const { pay_url } = await subscribeCrypto(selected, { product });
      openTelegramLink(pay_url);
      // Крипто-платёж подтверждается вебхуком асинхронно (не сразу, как
      // Stars) — статус подписки обновится при следующем открытии профиля.
    } catch {
      setError(t("subscribe.cryptoError"));
      haptic("error");
    } finally {
      setBusy(false);
    }
  }

  const isSubscribed = justPaid || me?.[cfg.subscribedKey];
  const expiresAt = me?.[cfg.expiresKey];
  const cycleDays = cfg.cycleKey ? me?.[cfg.cycleKey] : null;
  const daysLeft = daysUntil(expiresAt);
  const plan = plansData?.plans?.[selected];
  const compareRows = cfg.compareRows;
  const freeIndex = FREE_ROW_INDEX[product] ?? -1;
  // Экран продления (28.08.2026, макет "10 · Подписка"): даже с активной
  // подпиской остаются видны выгода, пикер тарифов и оплата, чтобы
  // продлить ЗАРАНЕЕ, не дожидаясь истечения (см. guro_logic.py::
  // subscription_expires_at — продление прибавляет к остатку, не
  // сбрасывает его). 05.09.2026 распространено на кабинеты рекрутера и
  // компании: раньше у них не было benefits, из-за чего showRenewal
  // оставался false и после оформления всё, кроме статуса, пряталось —
  // продлить из раздела «Подписка» было нельзя.
  const showRenewal = !!cfg.benefits;
  const showPlans = !isSubscribed || showRenewal;

  return (
    <div className="card">
      <h3>{t(cfg.titleKey)}</h3>
      {isSubscribed && (
        <div className="subscribe-status">
          <div className="subscribe-status-dot" />
          <div className="subscribe-status-info">
            <div className="subscribe-status-title">{t("subscribe.active")}</div>
            {expiresAt && (
              <div className="subscribe-status-meta">
                {t("subscribe.activeUntilDate", { date: formatDate(expiresAt) })}
                {daysLeft != null &&
                  ` · ${t("subscribe.daysLeft", {
                    count: daysLeft,
                    unit: lang === "ru" ? pluralRu(daysLeft, ["день", "дня", "дней"]) : daysLeft === 1 ? "day" : "days",
                  })}`}
              </div>
            )}
            {cycleDays > 0 && daysLeft != null && (
              <div className="subscribe-progress-track">
                <div
                  className="subscribe-progress-fill"
                  style={{ width: `${Math.max(0, Math.min(100, (daysLeft / cycleDays) * 100))}%` }}
                />
              </div>
            )}
          </div>
        </div>
      )}

      {!isSubscribed && !showRenewal && <div className="privacy-hint">{t(cfg.hintKey)}</div>}

      {showPlans && cfg.benefits ? (
        <>
          <div className="section-eyebrow" style={{ marginTop: isSubscribed ? 14 : 0 }}>
            {t("subscribe.benefitsTitle")}
          </div>
          {cfg.benefits.map((key) => (
            <div className="subscribe-benefit-row" key={key}>
              <IconCheck style={{ color: "var(--gold)" }} />
              <span>{t(key)}</span>
            </div>
          ))}
        </>
      ) : (
        !isSubscribed &&
        compareRows.map((key, i) => (
          <div className="compare-row" key={key}>
            <span>{t(key)}</span>
            <span className={i === freeIndex ? "free" : "paid"}>
              {i === freeIndex ? t("subscribe.free") : t("subscribe.paid")}
            </span>
          </div>
        ))
      )}

      {showPlans && (
        <>
          {showRenewal && <div className="section-eyebrow" style={{ marginTop: 16 }}>{t("subscribe.renewSectionTitle")}</div>}

          {plansData && (
            <div className="plan-picker">
              {Object.entries(plansData.plans).map(([key, p]) => (
                <button
                  key={key}
                  type="button"
                  className={`plan-card${selected === key ? " is-selected" : ""}`}
                  onClick={() => {
                    setSelected(key);
                    haptic("select");
                  }}
                >
                  {p.stars_price_full && <span className="plan-card-value-badge">{t("subscribe.bestValueBadge")}</span>}
                  <div className="plan-card-label">{p.label}</div>
                  {p.stars_price_full && (
                    <span className="plan-card-price-full">
                      {p.stars_price_full} <IconStar />
                    </span>
                  )}
                  <div className="plan-card-price-main">
                    {p.stars_price} <IconStar />
                  </div>
                  {p.stars_price_full && (
                    <div className="plan-card-badge">
                      {t("subscribe.economy", { amount: p.stars_price_full - p.stars_price })}
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}

          <button className="btn" onClick={onSubscribeStars} disabled={busy || !plan}>
            {busy
              ? t("subscribe.preparingInvoice")
              : t(isSubscribed ? "subscribe.renewStars" : "subscribe.payStars", { price: plan ? plan.stars_price : "…" })}
          </button>

          {plansData?.crypto_enabled && plan && (
            <button className="btn secondary" onClick={onSubscribeCrypto} disabled={busy}>
              {busy
                ? t("subscribe.preparingInvoice")
                : t("subscribe.payCrypto", { amount: plan.crypto_price_usd, asset: plan.crypto_asset })}
            </button>
          )}

          <Msg type="error">{error}</Msg>
        </>
      )}
    </div>
  );
}
