import { useEffect, useState } from "react";
import { search, searchByUserId, ApiError } from "../api.js";
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

// Компактная строка результата поиска по описанию (mode=list) — тап
// открывает полную карточку тем же кодом, что и обычный поиск по
// юзернейму (см. onOpen -> searchByUserId).
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
  const [query, setQuery] = useState("");
  const [state, setState] = useState(
    deepLinkTargetId ? { loading: true, data: null, error: null } : { loading: false, data: null, error: null },
  );

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

  // Одно поле на всё (10.08.2026): бэкенд сам решает, что это — точный
  // юзернейм (бесплатный тизер-профиль, mode=profile) или описание вроде
  // «менеджер в крипто» (платный поиск по открытым полям всего
  // комьюнити, mode=list), см. handle_search в guro_id_api.py.
  async function onSubmit(e) {
    e.preventDefault();
    const q = query.trim().replace(/^@/, "");
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
      </div>

      {state.loading && !state.data && <Spinner>Ищем…</Spinner>}

      {subscriptionRequired && (
        <div className="directory-paywall">
          <strong>Поиск по описанию — по подписке</strong>
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

      {state.data && state.data.mode === "list" && state.data.results.length === 0 && (
        <div className="partner-meta">Ничего не нашлось. Попробуйте другое описание.</div>
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

      {state.data && state.data.mode === "profile" && state.data.is_showcase && (
        <DeveloperShowcase data={state.data} />
      )}

      {state.data && state.data.mode === "profile" && !state.data.is_showcase && state.data.locked && (
        <LockedOverlay onUnlock={() => onNavigate("subscribe")}>
          <ResultCard p={state.data} />
        </LockedOverlay>
      )}

      {state.data && state.data.mode === "profile" && !state.data.is_showcase && !state.data.locked && (
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
