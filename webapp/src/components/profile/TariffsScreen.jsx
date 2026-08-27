import { useEffect, useState } from "react";
import { getPlans } from "../../api.js";
import { Spinner } from "../Shared.jsx";
import { useLang } from "../../i18n.jsx";

const PRODUCTS = ["guro_id", "recruiter", "company_basic", "company_pro"];

// Единый экран "Тарифы" (27.08.2026, ТЗ "экраны по ТЗ от 23.08") — раньше
// подписка была доступна только по частям, на каждом воркспейсе отдельно
// (SubscribeScreen product=...), тут все 4 продукта сразу + таблица
// лимитов на одном экране, как в макете. Цены живые (тот же /api/plans,
// что у SubscribeScreen — числа никогда не разъедутся с тем, что реально
// спишут), лимиты статичные (см. i18n.jsx tariffs.limits.*) — сами
// значения MVP-константы (guro_constants.py), макет их и подписывает
// как "MVP — гипотеза цены".
function useAllPlans() {
  const [state, setState] = useState({ loading: true, plans: {} });
  useEffect(() => {
    let cancelled = false;
    Promise.all(PRODUCTS.map((p) => getPlans({ product: p }).then((d) => [p, d.plans])))
      .then((pairs) => !cancelled && setState({ loading: false, plans: Object.fromEntries(pairs) }))
      .catch(() => !cancelled && setState({ loading: false, plans: {} }));
    return () => {
      cancelled = true;
    };
  }, []);
  return state;
}

function TariffCard({ product, plan, highlighted }) {
  const { t } = useLang();
  const monthly = plan?.monthly;
  const yearly = plan?.yearly;
  const discount = yearly?.stars_price_full
    ? Math.round((1 - yearly.stars_price / yearly.stars_price_full) * 100)
    : null;
  return (
    <div className={`card tariff-card${highlighted ? " is-highlighted" : ""}`}>
      <div className="project-head">
        <h3>{t(`tariffs.product.${product}.title`)}</h3>
        {highlighted && <span className="chip">{t("tariffs.hitBadge")}</span>}
      </div>
      {monthly && (
        <div className="tariff-price">
          <span className="tariff-price-main">${monthly.crypto_price_usd}{t("tariffs.perMonth")}</span>
          {yearly && (
            <span className="tariff-price-yearly">
              ${yearly.crypto_price_usd}{t("tariffs.perYear")}
              {discount != null ? ` · -${discount}%` : ""}
            </span>
          )}
        </div>
      )}
      <p className="partner-meta">{t(`tariffs.product.${product}.blurb`)}</p>
    </div>
  );
}

const LIMIT_ROWS = ["views", "requests", "vacancies", "approvals"];

export function TariffsScreen({ onBack }) {
  const { t } = useLang();
  const { loading, plans } = useAllPlans();
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <div className="card">
        <div className="project-head">
          <h3>{t("tariffs.title")}</h3>
          <span className="chip">{t("tariffs.mvpBadge")}</span>
        </div>
      </div>

      {loading && <Spinner>{t("tariffs.loading")}</Spinner>}
      {!loading && (
        <>
          <TariffCard product="guro_id" plan={plans.guro_id} />
          <TariffCard product="recruiter" plan={plans.recruiter} highlighted />
          <TariffCard product="company_basic" plan={plans.company_basic} />
          <TariffCard product="company_pro" plan={plans.company_pro} />
        </>
      )}

      <div className="card">
        <h3>{t("tariffs.limitsTitle")}</h3>
        {LIMIT_ROWS.map((key) => (
          <div className="tariff-limit-row" key={key}>
            <div className="tariff-limit-label">{t(`tariffs.limits.${key}Title`)}</div>
            <div className="partner-meta">{t(`tariffs.limits.${key}Value`)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
