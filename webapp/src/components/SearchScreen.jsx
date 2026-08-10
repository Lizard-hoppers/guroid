import { useEffect, useState } from "react";
import { search, searchByUserId, directorySearch, ApiError } from "../api.js";
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

function ResultCard({ p }) {
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
    </div>
  );
}

// Компактная строка результата directory-поиска (поиск по описанию, не по
// юзернейму) — тап открывает полную карточку тем же кодом, что и обычный
// поиск (см. onOpen -> searchByUserId в SearchScreen).
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

export function SearchScreen({ onNavigate, deepLinkTargetId, onConsumeDeepLink }) {
  const [username, setUsername] = useState("");
  const [state, setState] = useState(
    deepLinkTargetId ? { loading: true, data: null, error: null } : { loading: false, data: null, error: null },
  );
  const [query, setQuery] = useState("");
  const [dirState, setDirState] = useState({
    loading: false,
    results: null,
    truncated: false,
    subscriptionRequired: false,
    error: null,
  });

  // Заход по QR (App.jsx передаёт ?target=<id> ОДИН раз, дальше сам гасит
  // проп) — сразу тянем карточку по user_id, минуя ручной ввод юзернейма.
  // Тот же пейволл, что у обычного поиска (см. ResultCard/LockedOverlay ниже).
  useEffect(() => {
    if (!deepLinkTargetId) return;
    onConsumeDeepLink?.();
    searchByUserId(deepLinkTargetId)
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((error) => setState({ loading: false, data: null, error }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onSubmit(e) {
    e.preventDefault();
    const q = username.trim().replace(/^@/, "");
    if (!q) return;
    setState({ loading: true, data: null, error: null });
    try {
      const data = await search(q);
      setState({ loading: false, data, error: null });
      haptic("light");
    } catch (error) {
      setState({ loading: false, data: null, error });
      haptic("error");
    }
  }

  // Поиск по описанию ("менеджер в крипто") — список совпадений среди
  // ОТКРЫТЫХ (privacy-тумблерами) полей всего комьюнити. Целиком платная
  // фича: без подписки самого ищущего сервер отдаёт 402, список не строим.
  async function onDirectorySubmit(e) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setDirState({ loading: true, results: null, truncated: false, subscriptionRequired: false, error: null });
    try {
      const { results, truncated } = await directorySearch(q);
      setDirState({ loading: false, results, truncated, subscriptionRequired: false, error: null });
      haptic("light");
    } catch (error) {
      const subscriptionRequired = error instanceof ApiError && error.status === 402;
      setDirState({ loading: false, results: null, truncated: false, subscriptionRequired, error });
      haptic("error");
    }
  }

  async function openFromDirectory(userId) {
    setState({ loading: true, data: null, error: null });
    haptic("select");
    try {
      const data = await searchByUserId(userId);
      setState({ loading: false, data, error: null });
    } catch (error) {
      setState({ loading: false, data: null, error });
    }
  }

  return (
    <div>
      <div className="card">
        <h3>Поиск</h3>
        <form onSubmit={onSubmit}>
          <input
            type="text"
            placeholder="Поиск по юзернейму"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <button className="btn" type="submit" disabled={state.loading || !username.trim()}>
            {state.loading ? "Ищем…" : "Найти"}
          </button>
        </form>
      </div>

      <div className="card">
        <h3>Поиск по описанию</h3>
        <div className="partner-meta" style={{ marginBottom: 10 }}>
          Например: «менеджер в крипто». Ищем среди того, что участники сами открыли в профиле.
        </div>
        <form onSubmit={onDirectorySubmit}>
          <input
            type="text"
            placeholder="Кого вы ищете?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="btn" type="submit" disabled={dirState.loading || !query.trim()}>
            {dirState.loading ? "Ищем…" : "Искать"}
          </button>
        </form>

        {dirState.subscriptionRequired && (
          <div className="directory-paywall">
            <strong>Поиск по описанию — по подписке</strong>
            <p className="partner-meta">
              Без подписки доступен только точный поиск по юзернейму выше.
            </p>
            <button className="btn" style={{ width: "auto", padding: "10px 20px" }} onClick={() => onNavigate("subscribe")}>
              Оформить подписку
            </button>
          </div>
        )}

        {dirState.error && !dirState.subscriptionRequired && <Msg type="error">Ошибка поиска.</Msg>}

        {dirState.results && dirState.results.length === 0 && (
          <div className="partner-meta">Ничего не нашлось. Попробуйте другое описание.</div>
        )}

        {dirState.results && dirState.results.length > 0 && (
          <div className="directory-results">
            {dirState.results.map((r) => (
              <DirectoryRow key={r.user_id} r={r} onOpen={openFromDirectory} />
            ))}
            {dirState.truncated && (
              <div className="partner-meta" style={{ marginTop: 8 }}>
                Показаны не все совпадения — уточните запрос.
              </div>
            )}
          </div>
        )}
      </div>

      {state.loading && !state.data && <Spinner>Открываем профиль…</Spinner>}

      {state.error && (
        <Msg type="error">
          {state.error instanceof ApiError && state.error.code === "NOT_FOUND"
            ? "Такой участник не найден в GURO ID."
            : "Ошибка поиска."}
        </Msg>
      )}

      {state.data && state.data.is_showcase && <DeveloperShowcase data={state.data} />}

      {state.data && !state.data.is_showcase && state.data.locked && (
        <LockedOverlay onUnlock={() => onNavigate("subscribe")}>
          <ResultCard p={state.data} />
        </LockedOverlay>
      )}

      {state.data && !state.data.is_showcase && !state.data.locked && (
        <div>
          <ResultCard p={state.data} />
          <div className="card">
            <h3>История партнёрств контрагента</h3>
            <PartnersList partners={state.data.partners} emptyHint="Пока нет подтверждённых партнёрств." />
          </div>
        </div>
      )}
    </div>
  );
}
