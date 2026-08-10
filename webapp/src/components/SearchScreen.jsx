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

export function SearchScreen({ onNavigate, deepLinkTargetId, onConsumeDeepLink }) {
  const [username, setUsername] = useState("");
  const [state, setState] = useState(
    deepLinkTargetId ? { loading: true, data: null, error: null } : { loading: false, data: null, error: null },
  );

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
