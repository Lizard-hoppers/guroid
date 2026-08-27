import { useEffect, useState } from "react";
import { getMe, getPlans, subscribe, subscribeCrypto } from "../api.js";
import { Msg } from "./Shared.jsx";
import { openInvoice, openTelegramLink, haptic } from "../telegram.js";
import { formatDate } from "../utils.js";
import { useLang } from "../i18n.jsx";

const COMPARE_ROWS = [
  "subscribe.compare.workStatus",
  "subscribe.compare.rating",
  "subscribe.compare.search",
  "subscribe.compare.history",
];

// Кабинет рекрутера (Фаза 3, 12.08.2026) — та же оплата Stars+крипто, что у
// базовой подписки, параметризована по product вместо копии экрана.
const RECRUITER_COMPARE_ROWS = [
  "subscribe.compareRecruiter.rating",
  "subscribe.compareRecruiter.showcase",
  "subscribe.compareRecruiter.visibility",
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
    titleKey: "subscribe.titleGuro",
    hintKey: "subscribe.hintGuro",
    compareRows: COMPARE_ROWS,
  },
  recruiter: {
    workspace: "recruiter",
    subscribedKey: "is_recruiter_subscribed",
    expiresKey: "recruiter_subscription_expires_at",
    titleKey: "subscribe.titleRecruiter",
    hintKey: "subscribe.hintRecruiter",
    compareRows: RECRUITER_COMPARE_ROWS,
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
  },
  company_pro: {
    workspace: "company",
    subscribedKey: "is_company_subscribed",
    expiresKey: "company_subscription_expires_at",
    titleKey: "subscribe.titleCompanyPro",
    hintKey: "subscribe.hintCompanyPro",
    compareRows: COMPANY_COMPARE_ROWS,
  },
};

export function SubscribeScreen({ product = "guro_id", onSubscribed }) {
  const { t } = useLang();
  const cfg = PRODUCT_CONFIG[product] ?? PRODUCT_CONFIG.guro_id;
  const [me, setMe] = useState(null);
  const [plansData, setPlansData] = useState(null);
  const [selected, setSelected] = useState("monthly");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [justPaid, setJustPaid] = useState(false);

  useEffect(() => {
    getMe({ workspace: cfg.workspace })
      .then(setMe)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [justPaid]);

  useEffect(() => {
    getPlans({ product })
      .then(setPlansData)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [product]);

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
  const plan = plansData?.plans?.[selected];
  const compareRows = cfg.compareRows;
  const freeIndex = FREE_ROW_INDEX[product] ?? -1;

  return (
    <div className="card">
      <h3>{t(cfg.titleKey)}</h3>
      {isSubscribed ? (
        <Msg type="ok">
          {t("subscribe.active")}
          {expiresAt ? t("subscribe.activeUntil", { date: formatDate(expiresAt) }) : ""}.
        </Msg>
      ) : (
        <>
          <div className="privacy-hint">{t(cfg.hintKey)}</div>
          {compareRows.map((key, i) => (
            <div className="compare-row" key={key}>
              <span>{t(key)}</span>
              <span className={i === freeIndex ? "free" : "paid"}>
                {i === freeIndex ? t("subscribe.free") : t("subscribe.paid")}
              </span>
            </div>
          ))}

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
                  <div className="plan-card-label">{p.label}</div>
                  {p.stars_price_full && (
                    <span className="plan-card-price-full">{p.stars_price_full} ⭐</span>
                  )}
                  <div className="plan-card-price-main">{p.stars_price} ⭐</div>
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
            {busy ? t("subscribe.preparingInvoice") : t("subscribe.payStars", { price: plan ? plan.stars_price : "…" })}
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
