import { useEffect, useState } from "react";
import { search, searchByUserId, browseVertical, ApiError } from "../api.js";
import {
  Msg,
  MetricsRow,
  PartnersList,
  LockedOverlay,
  IdentityLine,
  WorkStatusBadge,
  Spinner,
} from "./Shared.jsx";
import { DeveloperShowcase } from "./DeveloperShowcase.jsx";
import { haptic } from "../telegram.js";

// Канонический список вертикалей — ровно constants.VERTICALS в боте (то,
// что реально пишется в profiles.vertical при регистрации, см.
// handlers/flow.py). Browse по вертикали (Фаза 2, 11.08.2026) matches
// именно эти значения (см. guro_id_api._directory_browse).
const VERTICALS = ["Gambling", "Betting", "Crypto", "Dating", "E-Commerce", "FinTech", "Nutra", "Other"];

// onWrite передаётся только для РАЗБЛОКИРОВАННОГО профиля (см. рендер ниже) —
// то же условие подписки смотрящего, что уже пускает писать первым в
// handle_send_message (storage.send_message), кнопка просто следует
// готовому серверному правилу, не дублирует его. onViewRecruiter — только
// если у человека есть активный кабинет рекрутера (has_recruiter_profile,
// Фаза 3), не запрашиваем recruiter-карточку вслепую на каждый профиль.
function ResultCard({ p, onWrite, onViewRecruiter }) {
  const heading = p.name === null ? "Скрыто" : p.name || (p.username ? `@${p.username}` : "Без имени");
  return (
    <div className="card">
      <h2 className={p.name === null ? "hidden-value" : ""}>{heading}</h2>
      <WorkStatusBadge status={p.work_status} />
      <IdentityLine label="Вертикаль: " value={p.vertical} />
      <IdentityLine label="Компания: " value={p.company} />
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
          ✉️ Написать
        </button>
      )}
      {p.has_recruiter_profile && onViewRecruiter && (
        <button
          type="button"
          className="btn secondary"
          style={{ marginTop: 8 }}
          onClick={onViewRecruiter}
        >
          🧑‍💼 Посмотреть как рекрутера
        </button>
      )}
    </div>
  );
}

// Карточка кабинета рекрутера контрагента (Фаза 3) — упрощённая версия
// ResultCard: своя вертикаль/компания/должность + CV/сайт/полезен, без
// рейтинга/партнёрств (те остаются свойством личного профиля).
function RecruiterResultCard({ p, onBackToPersonal }) {
  const heading = p.name || (p.username ? `@${p.username}` : "Без имени");
  return (
    <div className="card">
      <button type="button" className="subscreen-back" onClick={onBackToPersonal} style={{ marginBottom: 10 }}>
        ‹ Личный профиль
      </button>
      <h2>{heading}</h2>
      <IdentityLine label="Компания: " value={p.company} />
      <IdentityLine label="Вертикаль: " value={p.vertical} />
      <IdentityLine label="Должность: " value={p.profession} />
      {p.cv_text && <div className="partner-meta" style={{ marginTop: 8 }}>{p.cv_text}</div>}
      {p.website && <div className="partner-meta" style={{ marginTop: 4 }}>Сайт: {p.website}</div>}
      {p.offering && <div className="partner-meta" style={{ marginTop: 4 }}>Чем полезен: {p.offering}</div>}
    </div>
  );
}

// Компактная строка результата поиска по описанию/browse по вертикали
// (mode=list) — тап открывает полную карточку тем же кодом, что и обычный
// поиск по юзернейму (см. onOpen -> searchByUserId).
function DirectoryRow({ r, onOpen }) {
  const heading = r.name || (r.username ? `@${r.username}` : "Без имени");
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
  const [query, setQuery] = useState("");
  const [state, setState] = useState(
    deepLinkTargetId ? { loading: true, data: null, error: null } : { loading: false, data: null, error: null },
  );
  // "ТОП рейтинга" (Фаза 2) — переключатель сортировки для последнего
  // выполненного платного запроса (описание ИЛИ browse по вертикали),
  // lastQuery хранит, что именно перезапустить при переключении.
  const [sortTop, setSortTop] = useState(false);
  const [lastQuery, setLastQuery] = useState(null); // {kind: "q"|"vertical", value}

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
      const data = kind === "vertical" ? await browseVertical(value, { top }) : await search(value, { top });
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
    await runQuery("vertical", v, sortTop);
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
        <h3>Поиск</h3>
        <div className="partner-meta" style={{ marginBottom: 10 }}>
          Юзернейм — бесплатно (тизер-карточка). Описание, например «менеджер в крипто» —
          ищем среди того, что участники сами открыли в профиле (по подписке).
        </div>
        <form onSubmit={onSubmit}>
          <input
            type="text"
            placeholder="Юзернейм или описание"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="btn" type="submit" disabled={state.loading || !query.trim()}>
            {state.loading ? "Ищем…" : "Найти"}
          </button>
        </form>

        <div className="partner-meta" style={{ margin: "12px 0 6px" }}>
          Или посмотрите по вертикали, если не знаете юзернейм (по подписке):
        </div>
        <div className="vertical-chips">
          {VERTICALS.map((v) => (
            <button key={v} type="button" className="vertical-chip" onClick={() => onPickVertical(v)}>
              {v}
            </button>
          ))}
        </div>
      </div>

      {state.loading && !state.data && <Spinner>Ищем…</Spinner>}

      {subscriptionRequired && (
        <div className="directory-paywall">
          <strong>Поиск по описанию и вертикалям — по подписке</strong>
          <p className="partner-meta">
            Без подписки доступен только точный поиск по юзернейму.
          </p>
          <button className="btn" style={{ width: "auto", padding: "10px 20px" }} onClick={() => onNavigate("subscribe")}>
            Оформить подписку
          </button>
        </div>
      )}

      {state.error && !subscriptionRequired && (
        <Msg type="error">
          {state.error instanceof ApiError && state.error.code === "NOT_FOUND"
            ? "Такой участник не найден в GURO ID."
            : "Ошибка поиска."}
        </Msg>
      )}

      {state.data && state.data.mode === "list" && (
        <label className="checkbox-row" style={{ margin: "12px 2px" }}>
          <input type="checkbox" checked={sortTop} onChange={toggleTop} />
          🏆 Сначала высокий рейтинг
        </label>
      )}

      {state.data && state.data.mode === "list" && state.data.results.length === 0 && (
        <div className="partner-meta">Ничего не нашлось. Попробуйте другое описание или вертикаль.</div>
      )}

      {state.data && state.data.mode === "list" && state.data.results.length > 0 && (
        <div className="directory-results">
          {state.data.results.map((r) => (
            <DirectoryRow key={r.user_id} r={r} onOpen={openFromList} />
          ))}
          {state.data.truncated && (
            <div className="partner-meta" style={{ marginTop: 8 }}>
              Показаны не все совпадения — уточните запрос.
            </div>
          )}
        </div>
      )}

      {state.data && state.data.mode === "profile" && state.data.workspace === "recruiter" && !state.data.locked && (
        <RecruiterResultCard p={state.data} onBackToPersonal={backToPersonalCard} />
      )}

      {state.data && state.data.mode === "profile" && state.data.is_showcase && (
        <DeveloperShowcase data={state.data} />
      )}

      {state.data && state.data.mode === "profile" && !state.data.is_showcase &&
        state.data.workspace !== "recruiter" && state.data.locked && (
        <LockedOverlay onUnlock={() => onNavigate("subscribe")}>
          <ResultCard p={state.data} />
        </LockedOverlay>
      )}

      {state.data && state.data.mode === "profile" && !state.data.is_showcase &&
        state.data.workspace !== "recruiter" && !state.data.locked && (
        <div>
          <ResultCard p={state.data} onWrite={onOpenMessages} onViewRecruiter={viewRecruiterCard} />
          <div className="card">
            <h3>История партнёрств контрагента</h3>
            <PartnersList partners={state.data.partners} emptyHint="Пока нет подтверждённых партнёрств." />
          </div>
        </div>
      )}
    </div>
  );
}
