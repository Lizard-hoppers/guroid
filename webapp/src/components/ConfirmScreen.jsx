import { useEffect, useState } from "react";
import { createPartnership, getPendingRatings, ApiError } from "../api.js";
import { Msg, Spinner } from "./Shared.jsx";
import { RatePartnershipScreen } from "./RatePartnershipScreen.jsx";
import { haptic } from "../telegram.js";
import { useLang } from "../i18n.jsx";
import { formatDate } from "../utils.js";

// Список "Ждут вашей оценки" (28.08.2026, макет "07 · Сделки — шаг 2") —
// GET /api/partnerships/pending_ratings уже существовал на бэкенде
// неиспользуемым, тут наконец подключён к экрану. Только на базовом
// табе "Подтвердить" (не в под-сценариях "Подтвердить найм" из кабинетов
// Рекрутер/Компания/Вакансий — у тех есть onBack, см. условие в
// ConfirmScreen ниже) — это личные партнёрства пользователя, у
// найма-от-лица-кабинета своей оценки на этом шаге нет.
function PendingRatingsList({ items, onOpen }) {
  const { t } = useLang();
  if (!items || items.length === 0) return null;
  return (
    <div className="card">
      <h3>{t("confirm.pendingRatingsTitle")}</h3>
      {items.map((p) => (
        <button
          key={p.id}
          type="button"
          className="confirm-pending-rating-row"
          onClick={() => onOpen(p)}
        >
          <span>
            {p.name || (p.username ? `@${p.username}` : t("common.noName"))}
            <span className="partner-meta">
              {" · "}
              {t(p.ptype === "hire" ? "confirm.ptype.hire" : "confirm.ptype.deal")}
              {" · "}
              {formatDate(p.confirmed_at)}
            </span>
          </span>
          <span className="profile-menu-item-chevron">›</span>
        </button>
      ))}
    </div>
  );
}

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
  amountVisible: false,
  txHash: "",
  txNetwork: "",
};

// forcedType/onBack (26.08.2026, ТЗ "Гуро рекрутер каб", раздел 3-4) —
// кабинет "Рекрутер" использует ЭТУ ЖЕ форму, но с типом партнёрства
// жёстко "Найм" (переключатель скрыт) и переименованными подписями
// ("Подтвердить найм" вместо "Подтвердить партнёрство").
// prefill (26.08.2026, ТЗ "Recruitment — ВАКАНСИИ", раздел 5.4) — кнопка
// "Подтвердить найм" из отклика на вакансию подставляет username кандидата
// + вертикаль вакансии; грейд/должность своих полей тут не имеют — вместо
// расширения схемы партнёрства сложены в свободный "offer" (минимально
// инвазивная интерпретация, ТЗ этого явно не описывает).
// asCompany (27.08.2026, ТЗ "Роли и команда", раздел 6) — эта форма
// открыта ИЗ кабинета "Компания" ("действую как <бренд>"): сделка попадает
// в общую историю компании, лимит новых заявок — на компанию в целом.
// Фиксированный контекст всей сессии формы, не отдельный переключатель на
// каждую заявку — раз уж ты внутри кабинета компании, ты действуешь от
// её лица (та же логика, что уже принята для сообщений via_workspace).
export function ConfirmScreen({ forcedType, prefill, asCompany, onBack }) {
  const { t } = useLang();
  const [form, setForm] = useState(() => ({
    ...EMPTY_FORM,
    ...(forcedType ? { ptype: forcedType } : {}),
    ...(prefill || {}),
  }));
  const [state, setState] = useState({ loading: false, ok: false, error: null });
  // "Ждут вашей оценки" + экран оценки, Шаг 2 (28.08.2026) — только на
  // базовом табе "Подтвердить" (onBack не передан извне, см. App.jsx), не
  // в под-сценариях "Подтвердить найм" из кабинетов (у тех есть onBack).
  const showPendingRatings = !onBack;
  const [pendingRatings, setPendingRatings] = useState(null);
  const [rating, setRating] = useState(null); // выбранное партнёрство для RatePartnershipScreen

  function loadPendingRatings() {
    if (!showPendingRatings) return;
    getPendingRatings()
      .then(({ results }) => setPendingRatings(results))
      .catch(() => setPendingRatings([]));
  }

  useEffect(loadPendingRatings, []); // eslint-disable-line react-hooks/exhaustive-deps

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function onSubmit(e) {
    e.preventDefault();
    const q = form.confirmerUsername.trim().replace(/^@/, "");
    if (!q) return;
    setState({ loading: true, ok: false, error: null });
    try {
      await createPartnership({ ...form, confirmerUsername: q, asCompany });
      setState({ loading: false, ok: true, error: null });
      setForm(forcedType ? { ...EMPTY_FORM, ptype: forcedType } : EMPTY_FORM);
      haptic("success");
    } catch (error) {
      setState({ loading: false, ok: false, error });
      haptic("error");
    }
  }

  const errorText = state.error
    ? state.error instanceof ApiError && state.error.code === "DAILY_REQUEST_LIMIT_REACHED"
      ? t("confirm.error.DAILY_REQUEST_LIMIT_REACHED", { date: formatDate(state.error.details?.resets_at) })
      : t((state.error instanceof ApiError && ERROR_KEYS[state.error.code]) || "confirm.error.generic")
    : null;

  if (rating) {
    return (
      <RatePartnershipScreen
        partnership={rating}
        onBack={() => setRating(null)}
        onDone={() => {
          setRating(null);
          loadPendingRatings();
        }}
      />
    );
  }

  return (
    <div>
      {showPendingRatings && pendingRatings === null && <Spinner>{t("messages.loading")}</Spinner>}
      {showPendingRatings && <PendingRatingsList items={pendingRatings} onOpen={setRating} />}
      <div className="card">
        {onBack && (
          <button type="button" className="subscreen-back" onClick={onBack}>
            {t("common.back")}
          </button>
        )}
        <h3>{t(forcedType === "hire" ? "confirm.title.hire" : "confirm.title")}</h3>
        <div className="confirm-step-label">{t("confirm.stepLabel")}</div>
        {asCompany && <div className="company-verify-status is-verified">{t("confirm.asCompanyHint")}</div>}
        <div className="privacy-hint">{t("confirm.hint")}</div>
        <form onSubmit={onSubmit}>
        <label>{t("confirm.usernameLabel")}</label>
        <input
          type="text"
          placeholder={t("confirm.usernamePlaceholder")}
          value={form.confirmerUsername}
          onChange={(e) => set("confirmerUsername", e.target.value)}
        />
        {!forcedType && (
          <>
            <label>{t("confirm.ptypeLabel")} *</label>
            <div className="vertical-chips">
              <button
                type="button"
                className={`vertical-chip${form.ptype === "deal" ? " is-selected" : ""}`}
                onClick={() => set("ptype", "deal")}
              >
                {t("confirm.ptype.deal")}
              </button>
              <button
                type="button"
                className={`vertical-chip${form.ptype === "hire" ? " is-selected" : ""}`}
                onClick={() => set("ptype", "hire")}
              >
                {t("confirm.ptype.hire")}
              </button>
            </div>
            <p className="partner-meta">{t("confirm.ptypeHint")}</p>
          </>
        )}
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
    </div>
  );
}
