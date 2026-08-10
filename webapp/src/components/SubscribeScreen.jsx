import { useEffect, useState } from "react";
import { getMe, subscribe } from "../api.js";
import { Msg } from "./Shared.jsx";
import { openInvoice, haptic } from "../telegram.js";
import { formatDate } from "../utils.js";

const COMPARE_ROWS = [
  { label: "Видно, что в комьюнити есть рейтинги", tier: "free" },
  { label: "Полный поиск по юзернейму", tier: "paid" },
  { label: "История партнёрств контрагента", tier: "paid" },
];

export function SubscribeScreen() {
  const [me, setMe] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [justPaid, setJustPaid] = useState(false);

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch(() => {});
  }, [justPaid]);

  async function onSubscribe() {
    setBusy(true);
    setError("");
    try {
      const { invoice_link } = await subscribe();
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

  const isSubscribed = justPaid || me?.is_subscribed;

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
            Комьюнити и рейтинги видно всем бесплатно. Полный поиск и
            просмотр чужих профилей — по подписке.
          </div>
          {COMPARE_ROWS.map((r) => (
            <div className="compare-row" key={r.label}>
              <span>{r.label}</span>
              <span className={r.tier}>{r.tier === "free" ? "бесплатно" : "по подписке"}</span>
            </div>
          ))}
          <button className="btn" onClick={onSubscribe} disabled={busy}>
            {busy ? "Готовим счёт…" : "Оформить подписку · Telegram Stars"}
          </button>
          <Msg type="error">{error}</Msg>
        </>
      )}
    </div>
  );
}
