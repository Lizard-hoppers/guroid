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

// Кабинет рекрутера (Фаза 3, 12.08.2026) — та же оплата Stars+крипто, что у
// базовой подписки, параметризована по product вместо копии экрана.
const RECRUITER_COMPARE_ROWS = [
  { label: "Рейтинг и партнёрства (общие с личным профилем)", tier: "free" },
  { label: "Отдельная витрина: имя/компания/CV рекрутера", tier: "paid" },
  { label: "Видимость витрины другим участникам GURO ID", tier: "paid" },
];

export function SubscribeScreen({ product = "guro_id", onSubscribed }) {
  const isRecruiter = product === "recruiter";
  const [me, setMe] = useState(null);
  const [plansData, setPlansData] = useState(null);
  const [selected, setSelected] = useState("monthly");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [justPaid, setJustPaid] = useState(false);

  useEffect(() => {
    getMe({ workspace: isRecruiter ? "recruiter" : undefined })
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
      setError("Не получилось создать счёт. Попробуйте ещё раз.");
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
      setError("Не получилось создать крипто-счёт. Попробуйте ещё раз.");
      haptic("error");
    } finally {
      setBusy(false);
    }
  }

  const isSubscribed = justPaid || (isRecruiter ? me?.is_recruiter_subscribed : me?.is_subscribed);
  const expiresAt = isRecruiter ? me?.recruiter_subscription_expires_at : me?.subscription_expires_at;
  const plan = plansData?.plans?.[selected];

  return (
    <div className="card">
      <h3>{isRecruiter ? "Подписка на кабинет рекрутера" : "Подписка GURO ID"}</h3>
      {isSubscribed ? (
        <Msg type="ok">
          Подписка активна
          {expiresAt ? ` до ${formatDate(expiresAt)}` : ""}.
        </Msg>
      ) : (
        <>
          <div className="privacy-hint">
            {isRecruiter
              ? "Кабинет рекрутера — отдельная подписка поверх базовой GURO ID: своя витрина " +
                "(имя/компания/CV), не влияет на личный профиль. Рейтинг и партнёрства остаются общими."
              : "Без активной подписки ваш рейтинг и история сделок скрыты — ни вам, ни другим " +
                "(данные не удаляются, подписка просто держит их видимыми). Полный поиск и " +
                "просмотр чужих профилей — тоже по подписке."}
          </div>
          {(isRecruiter ? RECRUITER_COMPARE_ROWS : COMPARE_ROWS).map((r) => (
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
