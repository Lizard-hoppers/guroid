import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { getQr } from "../../api.js";
import { Msg, Spinner } from "../Shared.jsx";

export function QrSubscreen({ onBack }) {
  const [state, setState] = useState({ loading: true, dataUrl: null, error: null });

  useEffect(() => {
    let cancelled = false;
    getQr()
      .then(async ({ deeplink }) => {
        const dataUrl = await QRCode.toDataURL(deeplink, {
          margin: 1,
          width: 480,
          color: { dark: "#0e2a1c", light: "#ffffff" },
        });
        if (!cancelled) setState({ loading: false, dataUrl, error: null });
      })
      .catch((error) => !cancelled && setState({ loading: false, dataUrl: null, error }));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        ‹ Профиль
      </button>
      <div className="card qr-card">
        <h3>Мой QR</h3>
        {state.loading && <Spinner>Готовим QR…</Spinner>}
        {state.error && <Msg type="error">Не удалось получить QR. Попробуйте позже.</Msg>}
        {state.dataUrl && (
          <>
            <img src={state.dataUrl} alt="QR-код профиля GURO ID" />
            <div className="partner-meta">
              Покажите этот код — сканирующий откроет ваш профиль в GURO ID через бота.
              Полную карточку увидят только с активной подпиской.
            </div>
          </>
        )}
      </div>
    </div>
  );
}
