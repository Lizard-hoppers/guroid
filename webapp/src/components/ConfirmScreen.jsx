import { useState } from "react";
import { createPartnership, ApiError } from "../api.js";
import { Msg } from "./Shared.jsx";
import { haptic } from "../telegram.js";
import { useLang } from "../i18n.jsx";

const ERROR_KEYS = {
  SELF_PARTNERSHIP: "confirm.error.SELF_PARTNERSHIP",
  RATE_LIMITED: "confirm.error.RATE_LIMITED",
  NO_CONFIRMER_PROFILE: "confirm.error.NO_CONFIRMER_PROFILE",
  INVALID_TYPE: "confirm.error.generic",
  INVALID_NETWORK: "confirm.error.generic",
};

const EMPTY_FORM = {
  confirmerUsername: "",
  ptype: "deal",
  vertical: "",
  geo: "",
  offer: "",
  amountReceived: "",
  amountPaid: "",
  review: "",
  amountVisible: false,
  txHash: "",
  txNetwork: "",
};

export function ConfirmScreen() {
  const { t } = useLang();
  const [form, setForm] = useState(EMPTY_FORM);
  const [state, setState] = useState({ loading: false, ok: false, error: null });

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function onSubmit(e) {
    e.preventDefault();
    const q = form.confirmerUsername.trim().replace(/^@/, "");
    if (!q) return;
    setState({ loading: true, ok: false, error: null });
    try {
      await createPartnership({ ...form, confirmerUsername: q });
      setState({ loading: false, ok: true, error: null });
      setForm(EMPTY_FORM);
      haptic("success");
    } catch (error) {
      setState({ loading: false, ok: false, error });
      haptic("error");
    }
  }

  const errorText = state.error
    ? t((state.error instanceof ApiError && ERROR_KEYS[state.error.code]) || "confirm.error.generic")
    : null;

  return (
    <div className="card">
      <h3>{t("confirm.title")}</h3>
      <div className="privacy-hint">{t("confirm.hint")}</div>
      <form onSubmit={onSubmit}>
        <label>{t("confirm.usernameLabel")}</label>
        <input
          type="text"
          placeholder={t("confirm.usernameLabel")}
          value={form.confirmerUsername}
          onChange={(e) => set("confirmerUsername", e.target.value)}
        />
        <label>{t("confirm.ptypeLabel")}</label>
        <select value={form.ptype} onChange={(e) => set("ptype", e.target.value)}>
          <option value="deal">{t("confirm.ptype.deal")}</option>
          <option value="hire">{t("confirm.ptype.hire")}</option>
        </select>
        <label>{t("confirm.verticalLabel")}</label>
        <input
          type="text"
          placeholder={t("confirm.verticalLabel")}
          value={form.vertical}
          onChange={(e) => set("vertical", e.target.value)}
        />
        <label>{t("confirm.geoLabel")}</label>
        <input
          type="text"
          placeholder={t("confirm.geoPlaceholder")}
          value={form.geo}
          onChange={(e) => set("geo", e.target.value)}
        />
        <label>{t("confirm.offerLabel")}</label>
        <input
          type="text"
          placeholder={t("confirm.offerPlaceholder")}
          value={form.offer}
          onChange={(e) => set("offer", e.target.value)}
        />
        <label>{t("confirm.amountLabel")}</label>
        <div className="amount-row">
          <input
            type="number"
            inputMode="decimal"
            placeholder={t("confirm.amountReceivedPlaceholder")}
            value={form.amountReceived}
            onChange={(e) => set("amountReceived", e.target.value)}
          />
          <input
            type="number"
            inputMode="decimal"
            placeholder={t("confirm.amountPaidPlaceholder")}
            value={form.amountPaid}
            onChange={(e) => set("amountPaid", e.target.value)}
          />
        </div>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.amountVisible}
            onChange={(e) => set("amountVisible", e.target.checked)}
          />
          {t("confirm.amountVisible")}
        </label>
        <label>{t("confirm.txHashLabel")}</label>
        <input
          type="text"
          placeholder={t("confirm.txHashPlaceholder")}
          value={form.txHash}
          onChange={(e) => set("txHash", e.target.value)}
        />
        <div className="privacy-hint" style={{ marginTop: -6, marginBottom: 10 }}>
          {t("confirm.txHashHint")}
        </div>
        {form.txHash.trim() && (
          <>
            <label>{t("confirm.txNetworkLabel")}</label>
            <select value={form.txNetwork} onChange={(e) => set("txNetwork", e.target.value)}>
              <option value="">{t("confirm.txNetworkPlaceholder")}</option>
              <option value="tron">TRON (TRC20)</option>
              <option value="ethereum">Ethereum (ERC20)</option>
              <option value="bsc">BNB Smart Chain (BEP20)</option>
            </select>
          </>
        )}
        <label>{t("confirm.reviewLabel")}</label>
        <textarea
          rows={3}
          placeholder={t("confirm.reviewPlaceholder")}
          value={form.review}
          onChange={(e) => set("review", e.target.value)}
        />
        <button
          className="btn"
          type="submit"
          disabled={
            state.loading || !form.confirmerUsername.trim() ||
            (!!form.txHash.trim() && !form.txNetwork)
          }
        >
          {state.loading ? t("confirm.submitting") : t("confirm.submit")}
        </button>
      </form>
      <Msg type="error">{errorText}</Msg>
      <Msg type="ok">{state.ok ? t("confirm.sentOk") : null}</Msg>
    </div>
  );
}
