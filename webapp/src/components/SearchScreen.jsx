import { useEffect, useState } from "react";
import { search, searchByUserId, browseVertical, browseResumes, ApiError } from "../api.js";
import {
  Msg,
  MetricsRow,
  PartnersList,
  LockedOverlay,
  IdentityLine,
  WorkStatusBadge,
  Spinner,
  CvReadOnly,
} from "./Shared.jsx";
import { haptic } from "../telegram.js";
import { useLang } from "../i18n.jsx";
import { ensureHttpUrl, initialOf } from "../utils.js";

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
        />
        {onWrite && (
          <button
            type="button"
            className="btn secondary"
            style={{ marginTop: 12 }}
            onClick={() => onWrite(p.user_id)}
          >
            {t("messageBtn")}
          </button>
        )}
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
      {/* CV чужого профиля (16.08.2026) — раньше нигде не отображался при
          просмотре (бэкенд уже отдавал все поля, фронт их просто не рисовал).
          Отдельная карточка, не вложенная в основную — CvReadOnly сама
          решает, рисовать ли себя (пусто, если ни одного поля CV не
          заполнено/не открыто владельцем через show_cv). */}
      <CvReadOnly profile={p} />
    </>
  );
}

// Карточка кабинета рекрутера контрагента (Фаза 3) — упрощённая версия
// ResultCard: своя вертикаль/компания/должность + CV/сайт/полезен, без
// рейтинга/партнёрств (те остаются свойством личного профиля).
function RecruiterResultCard({ p, onBackToPersonal }) {
  const { t } = useLang();
  const heading = p.name || (p.username ? `@${p.username}` : t("common.noName"));
  return (
    <div className="card">
      <button type="button" className="subscreen-back" onClick={onBackToPersonal} style={{ marginBottom: 10 }}>
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
    </div>
  );
}

// Карточка кабинета "Компания" контрагента (Фаза 5, 17.08.2026) — зеркало
// RecruiterResultCard: бренд-страница работодателя, без рейтинга/партнёрств.
function CompanyResultCard({ p, onBackToPersonal }) {
  const { t } = useLang();
  const heading = p.name || (p.username ? `@${p.username}` : t("common.noName"));
  return (
    <div className="card">
      <button type="button" className="subscreen-back" onClick={onBackToPersonal} style={{ marginBottom: 10 }}>
        {t("common.backToPersonal")}
      </button>
      <div className="profile-header-card">
        {p.logo_url ? (
          <img className="profile-avatar" src={p.logo_url} alt="" />
        ) : (
          <div className="profile-avatar-fallback">{initialOf(p.name)}</div>
        )}
        <div className="profile-header-info">
          <h2 className={p.name === null ? "hidden-value" : ""}>{heading}</h2>
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
    </div>
  );
}

// Компактная строка результата поиска по описанию/browse по вертикали
// (mode=list) — тап открывает полную карточку тем же кодом, что и обычный
// поиск по юзернейму (см. onOpen -> searchByUserId).
function DirectoryRow({ r, onOpen }) {
  const { t } = useLang();
  const heading = r.name || (r.username ? `@${r.username}` : t("common.noName"));
  return (
    <button type="button" className="directory-row" onClick={() => onOpen(r.user_id)}>
      <div className="directory-row-main">
        <div className="directory-row-name">{heading}</div>
        <div className="partner-meta">
          {[r.profession, r.company, r.vertical].filter(Boolean).join(" · ") || "—"}
        </div>
        <WorkStatusBadge status={r.work_status} />
      </div>
      <span className="profile-menu-item-chevron">›</span>
    </button>
  );
}

export function SearchScreen({ onNavigate, deepLinkTargetId, onConsumeDeepLink, onOpenMessages }) {
  const { t } = useLang();
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
    searchByUserId(deepLinkTargetId)
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

  // Одно поле на всё (10.08.2026): бэкенд сам решает, что это — точный
  // юзернейм (бесплатный тизер-профиль, mode=profile) или описание вроде
  // «менеджер в крипто» (платный поиск по открытым полям всего
  // комьюнити, mode=list), см. handle_search в guro_id_api.py.
  async function onSubmit(e) {
    e.preventDefault();
    const q = query.trim().replace(/^@/, "");
    if (!q) return;
    await runQuery("q", q, sortTop);
  }

  async function onPickVertical(v) {
    setQuery("");
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
    setState({ loading: true, data: null, error: null });
    haptic("select");
    try {
      const data = await searchByUserId(userId);
      setState({ loading: false, data, error: null });
    } catch (error) {
      setState({ loading: false, data: null, error });
    }
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

  return (
    <div>
      <div className="card">
        <h3>{t("search.title")}</h3>
        <div className="partner-meta" style={{ marginBottom: 10 }}>
          {t("search.hint")}
        </div>
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

        <div className="partner-meta search-cabinets-hint">
          {t("search.cabinetsHint")}
        </div>

        <div className="partner-meta" style={{ margin: "12px 0 6px" }}>
          {t("search.browseHint")}
          {" "}
          <span className="search-demo-badge">{t("search.demoLabel")}</span>
        </div>
        <div className="vertical-chips">
          {VERTICALS.map((v) => (
            <button key={v} type="button" className="vertical-chip" onClick={() => onPickVertical(v)}>
              {v}
            </button>
          ))}
        </div>
        <label className="checkbox-row" style={{ marginTop: 10 }}>
          <input type="checkbox" checked={resumesOnly} onChange={(e) => setResumesOnly(e.target.checked)} />
          {t("search.resumesToggle")}
        </label>
        {resumesOnly && (
          <button type="button" className="onboarding-more-link" onClick={onShowAllResumes}>
            <span className="link-underline">{t("search.resumesShowAll")}</span>
          </button>
        )}
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
            : t("search.genericError")}
        </Msg>
      )}

      {state.data && state.data.mode === "list" && (
        <label className="checkbox-row" style={{ margin: "12px 2px" }}>
          <input type="checkbox" checked={sortTop} onChange={toggleTop} />
          {t("search.topToggle")}
        </label>
      )}

      {state.data && state.data.mode === "list" && state.data.results.length === 0 && (
        <div className="partner-meta">{t("search.emptyList")}</div>
      )}

      {state.data && state.data.mode === "list" && state.data.results.length > 0 && (
        <div className="directory-results">
          {state.data.results.map((r) => (
            <DirectoryRow key={r.user_id} r={r} onOpen={openFromList} />
          ))}
          {state.data.truncated && (
            <div className="partner-meta" style={{ marginTop: 8 }}>
              {t("search.truncated")}
            </div>
          )}
        </div>
      )}

      {state.data && state.data.mode === "profile" && state.data.workspace === "recruiter" && !state.data.locked && (
        <RecruiterResultCard p={state.data} onBackToPersonal={backToPersonalCard} />
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
