import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { getQr } from "../../api.js";
import { Msg, Spinner } from "../Shared.jsx";
import { useLang } from "../../i18n.jsx";

// workspace="recruiter" (26.08.2026, ТЗ "Гуро рекрутер каб", "Мой QR") —
// рабочая визитка кабинета, открывает у сканирующего РЕКРУТЕРСКУЮ карточку,
// не личный профиль (см. guro_id_api.handle_get_qr/handlers/flow.py).
export function QrSubscreen({ onBack, workspace }) {
  const { t } = useLang();
  const [state, setState] = useState({ loading: true, dataUrl: null, error: null });

  useEffect(() => {
    let cancelled = false;
    getQr({ workspace })
      .then(async ({ deeplink }) => {
        const dataUrl = await QRCode.toDataURL(deeplink, {
          margin: 1,
          width: 480,
          color: { dark: "#0b2024", light: "#ffffff" },
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
        {t("common.back")}
      </button>
      <div className="card qr-card">
        <h3>{t("qr.title")}</h3>
        {state.loading && <Spinner>{t("qr.preparing")}</Spinner>}
        {state.error && <Msg type="error">{t("qr.error")}</Msg>}
        {state.dataUrl && (
          <>
            <img src={state.dataUrl} alt="GURO ID QR" />
            <div className="partner-meta">{t("qr.hint")}</div>
          </>
        )}
      </div>
    </div>
  );
}
