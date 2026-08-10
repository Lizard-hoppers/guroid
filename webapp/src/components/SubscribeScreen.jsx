import { useEffect, useState } from "react";
import { getMe, getPlans, subscribe, subscribeCrypto } from "../api.js";
import { Msg } from "./Shared.jsx";
import { openInvoice, openTelegramLink, haptic } from "../telegram.js";
import { formatDate } from "../utils.js";

const COMPARE_ROWS = [
  { label: "Статус трудоустройства (виден всем)", tier: "free" },
  { label: "Ваш рейтинг и история сделок/найма", tier: "paid" },
  { label: "Полный поиск по юзернейму", tier: "paid" },
  { label: "История партнёрств контрагента", tier: "paid" },
];

export function SubscribeScreen() {
  const [me, setMe] = useState(null);
  const [plansData, setPlansData] = useState(null);
  const [selected, setSelected] = useState("monthly");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [justPaid, setJustPaid] = useState(false);

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch(() => {});
  }, [justPaid]);

  useEffect(() => {
    getPlans()
      .then(setPlansData)
      .catch(() => {});
  }, []);

  async function onSubscribeStars() {
    setBusy(true);
    setError("");
    try {
      const { invoice_link } = await subscribe(selected);
      openInvoice(invoice_link, (status) => {
        setBusy(false);
        if (status === "paid") {
          setJustPaid(true);
          haptic("success");
        }
      });
    } catch {
      setBusy(false);
      setError("Не получилось создать счёт. Попробуйте ещё раз.");
      haptic("error");
    }
  }

  async function onSubscribeCrypto() {
    setBusy(true);
    setError("");
    try {
      const { pay_url } = await subscribeCrypto(selected);
      openTelegramLink(pay_url);
      // Крипто-платёж подтверждается вебхуком асинхронно (не сразу, как
      // Stars) — статус подписки обновится при следующем открытии профиля.
    } catch {
      setError("Не получилось создать крипто-счёт. Попробуйте ещё раз.");
      haptic("error");
    } finally {
      setBusy(false);
    }
  }

  const isSubscribed = justPaid || me?.is_subscribed;
  const plan = plansData?.plans?.[selected];

  return (
    <div className="card">
      <h3>Подписка GURO ID</h3>
      {isSubscribed ? (
        <Msg type="ok">
          Подписка активна
          {me?.subscription_expires_at ? ` до ${formatDate(me.subscription_expires_at)}` : ""}.
        </Msg>
      ) : (
        <>
          <div className="privacy-hint">
            Без активной подписки ваш рейтинг и история сделок скрыты — ни вам, ни другим
            (данные не удаляются, подписка просто держит их видимыми). Полный поиск и
            просмотр чужих профилей — тоже по подписке.
          </div>
          {COMPARE_ROWS.map((r) => (
            <div className="compare-row" key={r.label}>
              <span>{r.label}</span>
              <span className={r.tier}>{r.tier === "free" ? "бесплатно" : "по подписке"}</span>
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
                      экономия {p.stars_price_full - p.stars_price} ⭐
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}

          <button className="btn" onClick={onSubscribeStars} disabled={busy || !plan}>
            {busy ? "Готовим счёт…" : `Оформить · ${plan ? `${plan.stars_price} ⭐` : "…"} Telegram Stars`}
          </button>

          {plansData?.crypto_enabled && plan && (
            <button className="btn secondary" onClick={onSubscribeCrypto} disabled={busy}>
              {busy
                ? "Готовим счёт…"
                : `Оплатить ${plan.crypto_price_usd} ${plan.crypto_asset} (крипто)`}
            </button>
          )}

          <Msg type="error">{error}</Msg>
        </>
      )}
    </div>
  );
}
