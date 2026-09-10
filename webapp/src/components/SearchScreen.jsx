import { useEffect, useRef, useState } from "react";
import { search, searchByUserId, browseVertical, browseResumes, requestJoinCompany, ApiError } from "../api.js";
import {
  Msg,
  MetricsRow,
  PartnersList,
  LockedOverlay,
  IdentityLine,
  WorkStatusBadge,
  Spinner,
  CharacteristicButton,
} from "./Shared.jsx";
import { useWorkspaceCaps } from "./VacanciesScreen.jsx";
import { RecruiterCandidatesScreen } from "./profile/RecruiterCandidatesScreen.jsx";
import { haptic } from "../telegram.js";
import { useLang } from "../i18n.jsx";
import { IconCheck, IconLock } from "./Icons.jsx";
import { ensureHttpUrl, initialOf, formatDate } from "../utils.js";

// Канонический список вертикалей — ровно constants.VERTICALS в боте (то,
// что реально пишется в profiles.vertical при регистрации, см.
// handlers/flow.py). Browse по вертикали (Фаза 2, 11.08.2026) matches
// именно эти значения (см. guro_id_api._directory_browse). Значения не
// переводим — это канонические английские метки, показываются как есть
// в обоих языках интерфейса (та же логика, что и остальной раздел
// профиля, где vertical хранится/отображается по-английски).
const VERTICALS = ["Gambling", "Betting", "Crypto", "Dating", "E-Commerce", "FinTech", "Nutra", "Other"];

// onWrite передаётся только для РАЗБЛОКИРОВАННОГО профиля (см. рендер ниже) —
// то же условие подписки смотрящего, что уже пускает писать первым в
// handle_send_message (storage.send_message), кнопка просто следует
// готовому серверному правилу, не дублирует его. onViewRecruiter/
// onViewCompany — только если у человека есть активный кабинет
// (has_recruiter_profile/has_company_profile), не запрашиваем карточку
// вслепую на каждый профиль.
function ResultCard({ p, onWrite, onViewRecruiter, onViewCompany }) {
  const { t } = useLang();
  const heading = p.name === null ? t("common.hidden") : p.name || (p.username ? `@${p.username}` : t("common.noName"));
  return (
    <>
      <div className="card">
        <h2 className={p.name === null ? "hidden-value" : ""}>{heading}</h2>
        <WorkStatusBadge status={p.work_status} />
        <IdentityLine label={t("identity.vertical")} value={p.vertical} />
        <IdentityLine label={t("identity.company")} value={p.company} />
        <MetricsRow
          reputation={p.reputation_score}
          partnerships={p.confirmed_partnerships}
          daysInCommunity={p.days_in_community}
          showVisibilityHint
        />
        {/* Ряд "Написать" + "Характеристика" — как в макете, в одну строку.
            Кнопки кабинетов идут ПОСЛЕ ряда: в макете их нет вовсе, и
            вклиниваться между двумя основными действиями им незачем. */}
        <div className="contragent-actions">
          {onWrite && (
            <button
              type="button"
              className="btn secondary"
              onClick={() => onWrite(p.user_id)}
            >
              {t("messageBtn")}
            </button>
          )}
          {/* «Характеристика» (26.08.2026, по прямому запросу владельца) —
              офферы + CV чужого профиля ЗА КНОПКОЙ (было — всегда
              развёрнуто), любой подписчик может открыть у любого профиля. */}
          <CharacteristicButton profile={p} />
        </div>
        {p.has_recruiter_profile && onViewRecruiter && (
          <button
            type="button"
            className="btn secondary"
            style={{ marginTop: 8 }}
            onClick={onViewRecruiter}
          >
            {t("recruiterViewBtn")}
          </button>
        )}
        {p.has_company_profile && onViewCompany && (
          <button
            type="button"
            className="btn secondary"
            style={{ marginTop: 8 }}
            onClick={onViewCompany}
          >
            {t("companyViewBtn")}
          </button>
        )}
      </div>
    </>
  );
}

// Карточка кабинета рекрутера контрагента (Фаза 3) — упрощённая версия
// ResultCard: своя вертикаль/компания/должность + CV/сайт/полезен, без
// рейтинга/партнёрств (те остаются свойством личного профиля).
// onWrite (26.08.2026, ТЗ "Гуро рекрутер каб", 2.7 "Кнопка Написать на
// чужом профиле в режиме Рекрутер") — без неё кандидат, видящий ТОЛЬКО
// рекрутерскую витрину (личный профиль мог быть закрыт приватностью),
// не мог бы связаться вообще.
function RecruiterResultCard({ p, onBackToPersonal, onWrite }) {
  const { t } = useLang();
  const heading = p.name || (p.username ? `@${p.username}` : t("common.noName"));
  return (
    <div className="card">
      <button type="button" className="subscreen-back" onClick={onBackToPersonal} style={{ marginBottom: 12 }}>
        {t("common.backToPersonal")}
      </button>
      <div className="profile-header-card">
        {p.logo_url ? (
          <img className="profile-avatar" src={p.logo_url} alt="" />
        ) : (
          <div className="profile-avatar-fallback">{initialOf(p.name, p.company)}</div>
        )}
        <div className="profile-header-info">
          <h2 className={p.name === null ? "hidden-value" : ""}>{heading}</h2>
        </div>
      </div>
      <IdentityLine label={t("recruiterCard.company")} value={p.company} />
      <IdentityLine label={t("recruiterCard.vertical")} value={p.vertical} />
      <IdentityLine label={t("recruiterCard.profession")} value={p.profession} />
      {p.cv_text && <div className="partner-meta" style={{ marginTop: 8 }}>{p.cv_text}</div>}
      {p.website && (
        <div className="partner-meta" style={{ marginTop: 4 }}>
          {t("recruiterCard.website")}
          <a href={ensureHttpUrl(p.website)} target="_blank" rel="noopener noreferrer">{p.website}</a>
        </div>
      )}
      {p.offering && <div className="partner-meta" style={{ marginTop: 4 }}>{t("recruiterCard.offering")}{p.offering}</div>}
      {onWrite && (
        <button type="button" className="btn secondary" style={{ marginTop: 12 }} onClick={() => onWrite(p.user_id)}>
          {t("messageBtn")}
        </button>
      )}
    </div>
  );
}

// Карточка кабинета "Компания" контрагента (Фаза 5, 17.08.2026) — зеркало
// RecruiterResultCard: бренд-страница работодателя, без рейтинга/партнёрств.
// "Запросить присоединение" (27.08.2026, ТЗ "Роли и управление командой",
// раздел 3.1) — с карточки ЧУЖОЙ компании, если смотрящий пока не Владелец
// и не Админ ни в одной компании (can_join, см. _company_profile_response).
function JoinCompanyForm({ companyId }) {
  const { t } = useLang();
  const [position, setPosition] = useState("");
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({ busy: false, done: false, error: null });

  async function submit(e) {
    e.preventDefault();
    setState({ busy: true, done: false, error: null });
    try {
      await requestJoinCompany(companyId, position.trim() || null);
      setState({ busy: false, done: true, error: null });
      haptic("success");
    } catch (error) {
      haptic("error");
      setState({
        busy: false, done: false,
        error: error instanceof ApiError && error.code === "ALREADY_REQUESTED"
          ? t("team.join.alreadyRequested")
          : error instanceof ApiError && error.code === "ALREADY_IN_COMPANY"
            ? t("team.join.alreadyInCompany")
            : t("team.join.error"),
      });
    }
  }

  if (state.done) {
    return <div className="partner-meta" style={{ marginTop: 12 }}>{t("team.join.sentOk")}</div>;
  }

  if (!open) {
    return (
      <button type="button" className="btn secondary" style={{ marginTop: 12 }} onClick={() => setOpen(true)}>
        {t("team.join.requestBtn")}
      </button>
    );
  }

  return (
    <form onSubmit={submit} style={{ marginTop: 12 }}>
      <label>{t("team.join.positionLabel")}</label>
      <input
        type="text"
        placeholder={t("team.join.positionPlaceholder")}
        value={position}
        onChange={(e) => setPosition(e.target.value)}
      />
      <button className="btn" type="submit" disabled={state.busy}>
        {state.busy ? t("team.join.submitting") : t("team.join.submitBtn")}
      </button>
      <Msg type="error">{state.error}</Msg>
    </form>
  );
}

function CompanyResultCard({ p, onBackToPersonal }) {
  const { t } = useLang();
  const heading = p.name || (p.username ? `@${p.username}` : t("common.noName"));
  return (
    <div className="card">
      <button type="button" className="subscreen-back" onClick={onBackToPersonal} style={{ marginBottom: 12 }}>
        {t("common.backToPersonal")}
      </button>
      <div className="profile-header-card">
        {p.logo_url ? (
          <img className="profile-avatar" src={p.logo_url} alt="" />
        ) : (
          <div className="profile-avatar-fallback">{initialOf(p.name)}</div>
        )}
        <div className="profile-header-info">
          <h2 className={p.name === null ? "hidden-value" : ""}>
            {heading}
            {p.verified && (
              <span className="company-verified-badge" title={t("company.verify.verified")}>
                <IconCheck />
              </span>
            )}
          </h2>
        </div>
      </div>
      <IdentityLine label={t("companyCard.vertical")} value={p.vertical} />
      {p.description && <div className="partner-meta" style={{ marginTop: 8 }}>{p.description}</div>}
      {p.website && (
        <div className="partner-meta" style={{ marginTop: 4 }}>
          {t("companyCard.website")}
          <a href={ensureHttpUrl(p.website)} target="_blank" rel="noopener noreferrer">{p.website}</a>
        </div>
      )}
      {p.can_join && <JoinCompanyForm companyId={p.company_id} />}
      {p.is_member && <div className="partner-meta" style={{ marginTop: 12 }}>{t("team.join.alreadyMember")}</div>}
    </div>
  );
}

// Компактная строка результата поиска по описанию/browse по вертикали
// (mode=list) — тап открывает полную карточку тем же кодом, что и обычный
// поиск по юзернейму (см. onOpen -> searchByUserId).
// Экспортирован (26.08.2026) — переиспользуется в RecruiterCandidatesScreen.jsx
// ("Найти кандидата", ТЗ "Гуро рекрутер каб") без дублирования разметки.
// showAvatar/showRating (28.08.2026, макет "12 · Рекрутер — Поиск
// кандидатов") — опциональные, только RecruiterCandidatesScreen их
// включает; обычный поиск личного профиля выглядит как раньше.
export function DirectoryRow({ r, onOpen, showAvatar = false, showRating = false }) {
  const { t } = useLang();
  const heading = r.name || (r.username ? `@${r.username}` : t("common.noName"));
  // Юзернейм показываем всегда, а не только вместо отсутствующего имени
  // (06.09.2026, стр. 6 отчёта): тёзки с одинаковой должностью в одной
  // компании выглядели дословно одинаково и читались как дубли. Различает
  // их именно юзернейм — и он же нужен, чтобы человеку написать.
  const handle = r.username && r.name ? `@${r.username}` : null;
  return (
    <button type="button" className="directory-row" onClick={() => onOpen(r.user_id)}>
      {showAvatar && <div className="avatar-dot">{initialOf(r.name, r.username)}</div>}
      <div className="directory-row-main">
        <div className="directory-row-name">{heading}</div>
        {handle && <div className="directory-row-handle">{handle}</div>}
        <div className="partner-meta">
          {[r.profession, r.company, r.vertical].filter(Boolean).join(" · ") || "—"}
        </div>
        <WorkStatusBadge status={r.work_status} />
      </div>
      {/* Ноль вместо пустоты у неоплативших (стр. 11 отчёта): рейтинг
          гасится подписочным гейтом в null, и кружок пропадал совсем.
          Ноль здесь значит «рейтинг не открыт», а не «посчитан и равен
          нулю» — так решил владелец, чтобы кандидату было что исправлять. */}
      {showRating && (
        <div className="rating-preview-circle directory-row-rating">
          {typeof r.reputation_score === "number" ? Math.round(r.reputation_score) : 0}
        </div>
      )}
    </button>
  );
}

export function SearchScreen({ onNavigate, deepLinkTargetId, deepLinkWorkspace, onConsumeDeepLink, onOpenMessages }) {
  const { t } = useLang();
  const caps = useWorkspaceCaps();
  const hasCabinet = caps.recruiter || caps.company;
  // Список, из которого открыли карточку (стр. 9 отчёта) — чтобы вернуться
  // к нему, а не искать заново.
  const [listSnapshot, setListSnapshot] = useState(null);
  // Два режима раздела для владельцев кабинета (стр. 7 отчёта): «пробить по
  // юзернейму» и «найти кандидата». По умолчанию классика — она же
  // единственное, что видят все остальные.
  const [mode, setMode] = useState("classic"); // "classic" | "candidates"
  const [query, setQuery] = useState("");
  const [state, setState] = useState(
    deepLinkTargetId ? { loading: true, data: null, error: null } : { loading: false, data: null, error: null },
  );
  // "ТОП рейтинга" (Фаза 2) — переключатель сортировки для последнего
  // выполненного платного запроса (описание ИЛИ browse по вертикали),
  // lastQuery хранит, что именно перезапустить при переключении.
  const [sortTop, setSortTop] = useState(false);
  const [lastQuery, setLastQuery] = useState(null); // {kind: "q"|"vertical"|"resumes", value}
  // «Резюме» (Фаза 4, 12.08.2026) — не отдельный экран, а фильтр поверх
  // browse по вертикали: пока включён, клик по чипу вертикали ищет ТОЛЬКО
  // тех, кто отметил "Ищу работу" (см. browseResumes/_resume_browse).
  const [resumesOnly, setResumesOnly] = useState(false);

  // Заход по QR (App.jsx передаёт ?target=<id> ОДИН раз, дальше сам гасит
  // проп) — сразу тянем карточку по user_id, минуя ручной ввод.
  useEffect(() => {
    if (!deepLinkTargetId) return;
    onConsumeDeepLink?.();
    searchByUserId(deepLinkTargetId, deepLinkWorkspace ? { workspace: deepLinkWorkspace } : undefined)
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((error) => setState({ loading: false, data: null, error }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runQuery(kind, value, top) {
    setLastQuery({ kind, value });
    setState({ loading: true, data: null, error: null });
    try {
      let data;
      if (kind === "resumes") data = await browseResumes(value, { top });
      else if (kind === "vertical") data = await browseVertical(value, { top });
      else data = await search(value, { top });
      setState({ loading: false, data, error: null });
      haptic("light");
    } catch (error) {
      setState({ loading: false, data: null, error });
      haptic("error");
    }
  }

  // Раздел больше не встречает пустотой (стр. 10 отчёта): выбранная по
  // умолчанию вертикаль сразу показывает анкеты, а не ждёт, пока человек
  // ткнёт в уже подсвеченный чип. Без подписки запрос отдаст 402 — тогда
  // тихо оставляем экран пустым, пейволл тут объясняется отдельно.
  const autoLoadedRef = useRef(false);
  useEffect(() => {
    if (autoLoadedRef.current || deepLinkTargetId || mode !== "classic") return;
    autoLoadedRef.current = true;
    let alive = true;
    browseVertical(VERTICALS[0], { top: false })
      .then((data) => alive && setState({ loading: false, data, error: null }))
      .catch(() => {});
  }, [deepLinkTargetId, mode]);

  // Одно поле на всё (10.08.2026): бэкенд сам решает, что это — точный
  // юзернейм (бесплатный тизер-профиль, mode=profile) или описание вроде
  // «менеджер в крипто» (платный поиск по открытым полям всего
  // комьюнити, mode=list), см. handle_search в guro_id_api.py.
  async function onSubmit(e) {
    e.preventDefault();
    const q = query.trim().replace(/^@/, "");
    if (!q) return;
    // Иначе кнопка «к списку» после нового поиска вернула бы в прежние
    // результаты, которых человек уже не ждёт.
    setListSnapshot(null);
    await runQuery("q", q, sortTop);
  }

  // Подсветка выбранной вертикали (28.08.2026, макет "03 · Поиск") — раньше
  // не было НИКАКОГО визуального состояния "выбрано", хотя CSS для этого
  // (.vertical-chip.is-selected) уже существовал в styles.css неиспользуемым.
  // Gambling выбрана по умолчанию — единственная вертикаль, где сейчас
  // реальные данные (см. search.browseHint), макет показывает её активной.
  const [selectedVertical, setSelectedVertical] = useState(VERTICALS[0]);

  async function onPickVertical(v) {
    setQuery("");
    setSelectedVertical(v);
    await runQuery(resumesOnly ? "resumes" : "vertical", v, sortTop);
  }

  async function onShowAllResumes() {
    setQuery("");
    await runQuery("resumes", "", sortTop);
  }

  function toggleTop() {
    const next = !sortTop;
    setSortTop(next);
    if (lastQuery) runQuery(lastQuery.kind, lastQuery.value, next);
  }

  async function openFromList(userId) {
    // Список нужно запомнить ДО замены: без этого вернуться было некуда
    // (стр. 9 отчёта). Возврат потом обходится без запроса.
    setListSnapshot(state.data);
    setState({ loading: true, data: null, error: null });
    haptic("select");
    try {
      const data = await searchByUserId(userId);
      setState({ loading: false, data, error: null });
    } catch (error) {
      setState({ loading: false, data: null, error });
    }
  }

  function backToList() {
    if (!listSnapshot) return;
    haptic("select");
    setState({ loading: false, data: listSnapshot, error: null });
    setListSnapshot(null);
  }

  // Переключение личный/рекрутер для УЖЕ ОТКРЫТОГО чужого профиля (Фаза 3).
  async function viewRecruiterCard() {
    const userId = state.data?.user_id;
    if (!userId) return;
    setState({ loading: true, data: null, error: null });
    try {
      const data = await searchByUserId(userId, { workspace: "recruiter" });
      setState({ loading: false, data, error: null });
    } catch (error) {
      setState({ loading: false, data: null, error });
    }
  }

  // Переключение личный/компания для УЖЕ ОТКРЫТОГО чужого профиля (Фаза 5).
  async function viewCompanyCard() {
    const userId = state.data?.user_id;
    if (!userId) return;
    setState({ loading: true, data: null, error: null });
    try {
      const data = await searchByUserId(userId, { workspace: "company" });
      setState({ loading: false, data, error: null });
    } catch (error) {
      setState({ loading: false, data: null, error });
    }
  }

  async function backToPersonalCard() {
    const userId = state.data?.user_id;
    if (!userId) return;
    setState({ loading: true, data: null, error: null });
    try {
      const data = await searchByUserId(userId);
      setState({ loading: false, data, error: null });
    } catch (error) {
      setState({ loading: false, data: null, error });
    }
  }

  const subscriptionRequired = state.error instanceof ApiError && state.error.status === 402;

  // Возврат после всех хуков — иначе порядок вызовов между рендерами
  // разъехался бы. Экран кабинета переиспользуется как есть, копии нет.
  if (mode === "candidates") {
    return (
      <RecruiterCandidatesScreen onBack={() => setMode("classic")} onWrite={onOpenMessages} />
    );
  }

  return (
    <div>
      <div className="card">
        <h3>{t("search.title")}</h3>
        <div className="partner-meta" style={{ marginBottom: 12 }}>
          {t("search.hint")}
        </div>
        {/* Выбор режима — только тем, у кого кабинет оплачен: остальным
            выбирать не из чего (стр. 7 отчёта). */}
        {!caps.loading && hasCabinet && (
          <div className="search-mode-switch">
            <button
              type="button"
              className={`search-mode-btn${mode === "classic" ? " is-active" : ""}`}
              onClick={() => setMode("classic")}
            >
              {t("search.mode.classic")}
            </button>
            <button
              type="button"
              className={`search-mode-btn${mode === "candidates" ? " is-active" : ""}`}
              onClick={() => setMode("candidates")}
            >
              {t("search.mode.candidates")}
            </button>
          </div>
        )}

        <form onSubmit={onSubmit}>
          <input
            type="text"
            placeholder={t("search.placeholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="btn" type="submit" disabled={state.loading || !query.trim()}>
            {state.loading ? t("search.submitting") : t("search.submit")}
          </button>
        </form>

        {/* Призыв оформить кабинет — только тем, у кого его нет. Пока
            флаги не приехали, тоже молчим: показать оплатившему «оформите»
            хуже, чем показать плашку на полсекунды позже. */}
        {!caps.loading && !hasCabinet && (
          <div className="hint-block search-cabinets-hint">
            <IconLock /> {t("search.cabinetsHint")}
          </div>
        )}

        <div className="partner-meta" style={{ margin: "12px 0 6px" }}>
          {t("search.browseHint")}
        </div>
        <div className="vertical-chips">
          {VERTICALS.map((v) => (
            <button
              key={v}
              type="button"
              className={`vertical-chip${v === selectedVertical ? " is-selected" : ""}`}
              onClick={() => onPickVertical(v)}
            >
              {v}
            </button>
          ))}
        </div>
        <label className="checkbox-row" style={{ marginTop: 12 }}>
          <input type="checkbox" checked={resumesOnly} onChange={(e) => setResumesOnly(e.target.checked)} />
          {t("search.resumesToggle")}
        </label>
        {resumesOnly && (
          <button type="button" className="onboarding-more-link" onClick={onShowAllResumes}>
            <span className="link-underline">{t("search.resumesShowAll")}</span>
          </button>
        )}
        <label className="checkbox-row" style={{ marginTop: 12 }}>
          <input type="checkbox" checked={sortTop} onChange={toggleTop} />
          {t("search.topToggle")}
        </label>
      </div>

      {state.loading && !state.data && <Spinner>{t("search.submitting")}</Spinner>}

      {subscriptionRequired && (
        <div className="directory-paywall">
          <strong>{t("search.paywallTitle")}</strong>
          <p className="partner-meta">{t("search.paywallText")}</p>
          <button className="btn" style={{ width: "auto", padding: "10px 20px" }} onClick={() => onNavigate("subscribe")}>
            {t("rating.subscribeCta")}
          </button>
        </div>
      )}

      {state.error && !subscriptionRequired && (
        <Msg type="error">
          {state.error instanceof ApiError && state.error.code === "NOT_FOUND"
            ? t("search.notFound")
            : state.error instanceof ApiError && state.error.code === "VIEW_LIMIT_REACHED"
              ? t("search.viewLimitReached", { date: formatDate(state.error.details?.resets_at) })
              : t("search.genericError")}
        </Msg>
      )}

      {state.data && state.data.mode === "list" && state.data.results.length === 0 && (
        <div className="partner-meta">{t("search.emptyList")}</div>
      )}

      {state.data && state.data.mode === "list" && state.data.results.length > 0 && (
        <div className="directory-results">
          {state.data.results.map((r) => (
            <DirectoryRow key={r.user_id} r={r} onOpen={openFromList} showRating />
          ))}
          {state.data.truncated && (
            <div className="partner-meta" style={{ marginTop: 8 }}>
              {t("search.truncated")}
            </div>
          )}
        </div>
      )}

      {/* Кнопка появляется, только если мы действительно пришли из
          списка: у захода по QR или прямому юзернейму возвращаться некуда. */}
      {listSnapshot && state.data && state.data.mode === "profile" && (
        <button type="button" className="subscreen-back" onClick={backToList}>
          {t("search.backToList")}
        </button>
      )}

      {state.data && state.data.mode === "profile" && state.data.workspace === "recruiter" && !state.data.locked && (
        <RecruiterResultCard p={state.data} onBackToPersonal={backToPersonalCard} onWrite={onOpenMessages} />
      )}

      {state.data && state.data.mode === "profile" && state.data.workspace === "company" && !state.data.locked && (
        <CompanyResultCard p={state.data} onBackToPersonal={backToPersonalCard} />
      )}

      {/* 18.08.2026: раньше locked-кабинеты рекрутера/компании вообще не
          рендерились (ни один из блоков выше не совпадал) — владелец
          сообщил "нажимаю кнопку, ничего не происходит". Тизер + пейволл
          для этих двух воркспейсов у смотрящего без подписки. */}
      {state.data && state.data.mode === "profile" && state.data.workspace === "recruiter" && state.data.locked && (
        <LockedOverlay onUnlock={() => onNavigate("subscribe")}>
          <RecruiterResultCard p={state.data} onBackToPersonal={backToPersonalCard} />
        </LockedOverlay>
      )}

      {state.data && state.data.mode === "profile" && state.data.workspace === "company" && state.data.locked && (
        <LockedOverlay onUnlock={() => onNavigate("subscribe")}>
          <CompanyResultCard p={state.data} onBackToPersonal={backToPersonalCard} />
        </LockedOverlay>
      )}

      {state.data && state.data.mode === "profile" &&
        !state.data.workspace && state.data.locked && (
        <LockedOverlay onUnlock={() => onNavigate("subscribe")}>
          <ResultCard p={state.data} />
        </LockedOverlay>
      )}

      {state.data && state.data.mode === "profile" &&
        !state.data.workspace && !state.data.locked && (
        <div>
          <ResultCard
            p={state.data}
            onWrite={onOpenMessages}
            onViewRecruiter={viewRecruiterCard}
            onViewCompany={viewCompanyCard}
          />
          <div className="card">
            <h3>{t("rating.otherHistoryTitle")}</h3>
            <PartnersList partners={state.data.partners} emptyHint={t("rating.emptyOther")} />
          </div>
        </div>
      )}
    </div>
  );
}
