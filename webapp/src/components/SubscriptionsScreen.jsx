import { useEffect, useState } from "react";
import { getMe, getPlans } from "../api.js";
import { SubscribeScreen } from "./SubscribeScreen.jsx";
import { useLang } from "../i18n.jsx";

// Таб "Подписка" — ВСЕ подписки в одном месте и в одном формате
// (05.09.2026, просьба владельца). Раньше тут была полная форма только для
// базовой GURO ID, а Рекрутер и Компания шли строчками-ссылками в свои
// кабинеты, и оформить их можно было только там.
//
// Дублировать форму не пришлось: SubscribeScreen параметризован по product
// и сам рисует законченную карточку — заголовок, статус с остатком дней,
// список того, что даёт подписка, выбор периода и обе кнопки оплаты.
//
// Данные грузит ЭКРАН, а не каждый блок по отдельности: иначе три блока
// ходили в сеть сами, ответы приходили вразнобой и вёрстка дёргалась на
// каждом. Здесь всё уходит параллельно и кладётся ОДНИМ setState — одна
// перерисовка вместо трёх. Тарифы обоих тиров компании берём сразу, чтобы
// переключение Basic/Pro не дёргало ни сеть, ни вёрстку.
//
// Одним запросом обойтись нельзя: /api/me отдаёт три РАЗНЫЕ формы в
// зависимости от ?workspace= — это разные таблицы, а не срез одного объекта.
const PLAN_PRODUCTS = ["guro_id", "recruiter", "company_basic", "company_pro"];

export function SubscriptionsScreen() {
  const { t } = useLang();
  const [data, setData] = useState(null);
  // Тир компании выбирается ДО первой оплаты: Basic и Pro — два разных
  // product (см. PRODUCT_CONFIG в SubscribeScreen.jsx). После оплаты тир
  // зафиксирован на бэкенде, переключатель прячем. Та же логика, что в
  // CompanyHub — если менять, менять в обоих местах.
  const [tierChoice, setTierChoice] = useState("basic");

  function load() {
    Promise.allSettled([
      getMe(),
      getMe({ workspace: "recruiter" }),
      getMe({ workspace: "company" }),
      ...PLAN_PRODUCTS.map((product) => getPlans({ product })),
    ]).then((results) => {
      const value = (i) => (results[i].status === "fulfilled" ? results[i].value : null);
      setData({
        me: { guro_id: value(0), recruiter: value(1), company: value(2) },
        plans: Object.fromEntries(PLAN_PRODUCTS.map((p, i) => [p, value(3 + i)])),
      });
    });
  }
  useEffect(load, []);

  const company = data?.me.company;
  const companySubscribed = !!company?.is_company_subscribed;
  const companyProduct = companySubscribed
    ? company.company_tier === "pro" ? "company_pro" : "company_basic"
    : tierChoice === "pro" ? "company_pro" : "company_basic";

  return (
    <div>
      <SubscribeScreen
        product="guro_id"
        me={data ? data.me.guro_id : null}
        plans={data ? data.plans.guro_id : null}
      />
      <SubscribeScreen
        product="recruiter"
        me={data ? data.me.recruiter : null}
        plans={data ? data.plans.recruiter : null}
      />

      {!companySubscribed && (
        <div className="card">
          <h3>{t("company.title")}</h3>
          <p className="partner-meta">{t("company.upsellText")}</p>
          <div className="vertical-chips" style={{ marginTop: 12 }}>
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
      )}

      <SubscribeScreen
        product={companyProduct}
        me={data ? data.me.company : null}
        plans={data ? data.plans[companyProduct] : null}
        onSubscribed={load}
      />
    </div>
  );
}
