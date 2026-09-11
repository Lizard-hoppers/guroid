import { useEffect, useState } from "react";
import { createPartnership, getPendingRatings, getMe, ApiError } from "../api.js";
import { Msg, Spinner, PartnersList } from "./Shared.jsx";
import { RatePartnershipScreen } from "./RatePartnershipScreen.jsx";
import { haptic } from "../telegram.js";
import { useLang } from "../i18n.jsx";
import { IconCheck, IconCross, IconWarning } from "./Icons.jsx";
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

// "История партнёрств" (28.08.2026, макет "08 · История партнёрств") —
// ссылка с таба "Подтвердить" на уже существующий список подтверждённых
// партнёрств (тот же PartnerRow/PartnersList, что и "Профиль -> Мой
// рейтинг" — та подсказка/дашборд метрик остаётся как есть, не трогали,
// см. RatingSubscreen.jsx). Тут — просто сводка счётчиков по вердиктам
// (✅/⚠/❌), которой раньше не было НИГДЕ в приложении.
function PartnershipHistoryScreen({ partners, onBack }) {
  const { t } = useLang();
  const counts = (partners || []).reduce((acc, p) => {
    if (p.my_rating) acc[p.my_rating] = (acc[p.my_rating] || 0) + 1;
    return acc;
  }, {});
  return (
    <div className="card">
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <h3>{t("confirm.history.title")}</h3>
      <p className="partner-meta">
        <IconCheck style={{ color: "var(--gold)" }} /> {counts.success || 0} {t("confirm.history.successLabel")}
        {" · "}<IconWarning style={{ color: "var(--amber)" }} /> {counts.nuance || 0} {t("confirm.history.nuanceLabel")}
        {" · "}<IconCross style={{ color: "var(--danger)" }} /> {counts.problematic || 0} {t("confirm.history.problematicLabel")}
        {" · "}{t("confirm.history.allTime")}
      </p>
      <div className="privacy-hint">{t("confirm.history.hint")}</div>
      <PartnersList partners={partners} emptyHint={t("rating.emptyOwn")} allowRating />
    </div>
  );
}

const ERROR_KEYS = {
  SELF_PARTNERSHIP: "confirm.error.SELF_PARTNERSHIP",
  RATE_LIMITED: "confirm.error.RATE_LIMITED",
  NO_CONFIRMER_PROFILE: "confirm.error.NO_CONFIRMER_PROFILE",
  // Раньше эти две вели на общий текст «Не получилось отправить заявку»,
  // и человек не понимал, что именно поправить (05.09.2026, отчёт
  // тестирования). Теперь у каждой свой текст.
  INVALID_TYPE: "confirm.error.INVALID_TYPE",
  INVALID_NETWORK: "confirm.error.INVALID_NETWORK",
  COMPANY_SUBSCRIPTION_REQUIRED: "confirm.error.COMPANY_SUBSCRIPTION_REQUIRED",
  TX_HASH_REQUIRED: "confirm.error.TX_HASH_REQUIRED",
  // Занятый хеш (ТЗ «Hash_Uniqueness», раздел 3). Случай A разбирается
  // отдельно ниже — ему нужны имя контрагента и дата, а эта карта умеет
  // только код -> ключ.
  TX_HASH_ALREADY_USED: "confirm.error.TX_HASH_ALREADY_USED",
  TX_HASH_USED_BY_OWN: "confirm.error.TX_HASH_USED_BY_OWN",
};

// Случай A из раздела 3 ТЗ «Hash_Uniqueness»: имя контрагента и дата
// приходят вместе с кодом отказа — подставляем их в текст. Если сервер их
// почему-то не прислал, остаётся общая формулировка без подробностей.
function formatSubmitError(error, t) {
  const code = error instanceof ApiError ? error.code : null;
  if (code === "TX_HASH_USED_BY_OWN") {
    const username = error.details?.partner_username;
    const date = error.details?.partnership_date;
    if (username && date) {
      return t("confirm.error.TX_HASH_USED_BY_OWN", {
        partner: `@${username}`,
        date: formatPartnershipDate(date),
      });
    }
    return t("confirm.error.TX_HASH_USED_BY_OWN_SHORT");
  }
  return t((code && ERROR_KEYS[code]) || "confirm.error.generic");
}

// Дата приходит строкой из БД; показываем её так же, как в истории
// партнёрств — днём и месяцем, без времени.
function formatPartnershipDate(raw) {
  const parsed = new Date(String(raw).replace(" ", "T"));
  if (Number.isNaN(parsed.getTime())) return String(raw);
  return parsed.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

const EMPTY_FORM = {
  confirmerUsername: "",
  ptype: "deal",
  vertical: "",
  geo: "",
  offer: "",
  amountReceived: "",
  amountPaid: "",
  amountVisible: false,
  // "Анонимная сделка/найм" (11.09.2026) — по умолчанию ВЫКЛЮЧЕНА
  // (подтверждено владельцем): история партнёрств остаётся содержательной
  // для тех, кому анонимность не нужна, включают её сами.
  anonymous: false,
  // Безоплатное партнёрство (ТЗ раздел 9.1): факт сотрудничества был,
  // прямого платежа между сторонами — нет. Доступно для ОБОИХ типов.
  noPayment: false,
  txHash: "",
  txNetwork: "",
  isFlaggedFraud: false,
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
  // "История партнёрств" (28.08.2026, макет "08 · История партнёрств") —
  // partners тянем через getMe() (то же поле, что и "Профиль -> Мой
  // рейтинг"), только когда реально открыт экран истории (showHistory),
  // не на каждом заходе на таб "Подтвердить" — незачем лишний запрос,
  // пока пользователь им не воспользовался.
  const [showHistory, setShowHistory] = useState(false);
  const [historyPartners, setHistoryPartners] = useState(null);

  function loadPendingRatings() {
    if (!showPendingRatings) return;
    getPendingRatings()
      .then(({ results }) => setPendingRatings(results))
      .catch(() => setPendingRatings([]));
  }

  useEffect(loadPendingRatings, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!showHistory || historyPartners !== null) return;
    getMe()
      .then((data) => setHistoryPartners(data.partners || []))
      .catch(() => setHistoryPartners([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showHistory]);

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
      : formatSubmitError(state.error, t)
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

  if (showHistory) {
    return historyPartners === null ? (
      <Spinner>{t("messages.loading")}</Spinner>
    ) : (
      <PartnershipHistoryScreen partners={historyPartners} onBack={() => setShowHistory(false)} />
    );
  }

  return (
    <div>
      {/* Спиннер стоит НА МЕСТЕ будущего списка и заменяется им. Раньше
          рисовались оба сразу: спиннер отдельным блоком НАД списком, и
          когда данные приходили, он исчезал — всё нижележащее прыгало
          вверх на его высоту. */}
      {showPendingRatings &&
        (pendingRatings === null ? (
          <Spinner>{t("messages.loading")}</Spinner>
        ) : (
          <PendingRatingsList items={pendingRatings} onOpen={setRating} />
        ))}
      {showPendingRatings && (
        <div className="card">
          <button type="button" className="profile-menu-item" onClick={() => setShowHistory(true)}>
            <span>{t("confirm.historyLink")}</span>
            <span className="profile-menu-item-chevron">›</span>
          </button>
        </div>
      )}
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
        {/* В самом верху экрана (11.09.2026, просьба владельца) — решение
            "видно/анонимно" человек принимает ДО того, как начнёт вводить
            детали, а не в середине формы: включение сразу скрывает
            вертикаль/гео/видимость суммы ниже. */}
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.anonymous}
            onChange={(e) => set("anonymous", e.target.checked)}
          />
          {t("confirm.anonymousLabel")}
        </label>
        <div className="privacy-hint">{t("confirm.anonymousHint")}</div>
        <form onSubmit={onSubmit}>
        <label>{t("confirm.usernameLabel")} *</label>
        <input
          type="text"
          placeholder={t("confirm.usernamePlaceholder")}
          value={form.confirmerUsername}
          onChange={(e) => set("confirmerUsername", e.target.value)}
        />
        {!forcedType && (
          <>
            <label>{t("confirm.ptypeLabel")} *</label>
            <div className="vertical-chips vertical-chips--accent">
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
        {/* Вертикаль/гео описывают сделку для ПОСТОРОННИХ, листающих
            профиль, — анонимной сделке их заполнять незачем. */}
        {!form.anonymous && (
          <>
            <label>{t("confirm.verticalLabel")} *</label>
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
          </>
        )}
        <label>{t(form.anonymous ? "confirm.commentLabel" : "confirm.offerLabel")}{form.anonymous ? "" : " *"}</label>
        <input
          type="text"
          placeholder={t(form.anonymous ? "confirm.commentPlaceholder" : "confirm.offerPlaceholder")}
          value={form.offer}
          onChange={(e) => set("offer", e.target.value)}
        />
        {/* Над денежным блоком, чтобы человек увидел его ДО того, как
            начнёт заполнять суммы (ТЗ раздел 13). */}
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.noPayment}
            onChange={(e) => set("noPayment", e.target.checked)}
          />
          {t("confirm.noPaymentLabel")}
        </label>
        <div className="privacy-hint">{t("confirm.noPaymentHint")}</div>

        {!form.noPayment && (
          <>
        <label>{t("confirm.amountLabel")} *</label>
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
        <div className="privacy-hint" style={{ marginTop: 8 }}>
          {t("confirm.amountRequiredHint")}
        </div>
        {/* Бессмысленна в анонимном режиме — сделку целиком не видят
            третьи лица, отдельно скрывать сумму не от кого. */}
        {!form.anonymous && (
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.amountVisible}
              onChange={(e) => set("amountVisible", e.target.checked)}
            />
            {t("confirm.amountVisible")}
          </label>
        )}
        <label>{t("confirm.txHashLabel")} *</label>
        <input
          type="text"
          placeholder={t("confirm.txHashPlaceholder")}
          value={form.txHash}
          onChange={(e) => set("txHash", e.target.value)}
        />
        {/* Отступ положительный: раньше тут стоял marginTop: -6 и подсказка
            наезжала на поле ввода. */}
        <div className="privacy-hint" style={{ marginTop: 8 }}>
          {t("confirm.txHashHint")}
        </div>
        {/* Требование объясняется ДО того, как человек упрётся в неактивную
            кнопку: сама по себе звёздочка не говорит, почему без хеша
            нельзя («рекрутер каб.pdf», стр. 4). */}
        {!form.noPayment && !form.txHash.trim() && (
          <div className="tx-required-note">{t("confirm.txHashRequired")}</div>
        )}
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
          </>
        )}
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.isFlaggedFraud}
            onChange={(e) => set("isFlaggedFraud", e.target.checked)}
          />
          {t("confirm.flagFraudLabel")}
        </label>
        <button
          className="btn"
          type="submit"
          disabled={
            state.loading ||
            // Обязательные поля (05.09.2026): всё, кроме гео и хэша/ссылки.
            // Тип партнёрства не проверяем — у него есть значение по
            // умолчанию и пустым он не бывает.
            !form.confirmerUsername.trim() ||
            // Вертикаль/офер обязательны, только пока сделка НЕ анонимна —
            // в анонимном режиме это поле необязательный комментарий, а
            // вертикаль вообще не показывается.
            (!form.anonymous && !form.vertical.trim()) ||
            (!form.anonymous && !form.offer.trim()) ||
            // Сумма односторонняя: хватает любого одного из двух полей.
            // У безоплатного партнёрства денег нет вовсе — проверку суммы
            // и хеша выключаем целиком (ТЗ раздел 9.1).
            (!form.noPayment &&
              !String(form.amountReceived).trim() &&
              !String(form.amountPaid).trim()) ||
            (!form.noPayment && !!form.txHash.trim() && !form.txNetwork) ||
            // «Нет хеша — сделки не было» («рекрутер каб.pdf», стр. 4).
            // У безоплатного партнёрства перевода нет вовсе — не требуем.
            (!form.noPayment && !form.txHash.trim())
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
