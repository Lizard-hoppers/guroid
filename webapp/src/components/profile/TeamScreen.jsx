import { useEffect, useState } from "react";
import {
  getCompanyTeam, approveJoinRequest, rejectJoinRequest, removeCompanyMember, transferCompanyOwnership, ApiError,
} from "../../api.js";
import { Msg, Spinner } from "../Shared.jsx";
import { useLang } from "../../i18n.jsx";
import { haptic } from "../../telegram.js";
import { formatDate } from "../../utils.js";

// Экран "Команда" (ТЗ "Роли и управление командой", раздел 3.2, 27.08.2026)
// — таб "Запросы" (только Владельцу, сервер сам не отдаёт requests не-
// владельцу) + таб "Участники" (видно всем). Управляющие кнопки
// (Принять/Отклонить/Удалить/Передать владение) скрыты для Админа —
// он видит ровно то же самое, просто без кнопок (раздел 2 ТЗ: Админ не
// управляет составом команды).
export function TeamScreen({ onBack }) {
  const { t } = useLang();
  const [tab, setTab] = useState("members");
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [actionError, setActionError] = useState(null);

  function load() {
    setState((s) => ({ ...s, loading: true, error: null }));
    getCompanyTeam()
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((error) => setState({ loading: false, data: null, error }));
  }

  useEffect(load, []);
  useEffect(() => {
    if (state.data?.requests?.length > 0) setTab("requests");
  }, [state.data]);

  async function onApprove(requestId) {
    setActionError(null);
    try {
      await approveJoinRequest(requestId);
      haptic("success");
      load();
    } catch (error) {
      haptic("error");
      setActionError(
        error instanceof ApiError && error.code === "MEMBER_LIMIT_REACHED"
          ? t("team.errors.memberLimitReached", { limit: error.details?.limit })
          : error instanceof ApiError && error.code === "DAILY_APPROVAL_LIMIT_REACHED"
            ? t("team.errors.dailyApprovalLimitReached", { date: formatDate(error.details?.resets_at) })
            : t("team.errors.generic"),
      );
    }
  }

  async function onReject(requestId) {
    setActionError(null);
    try {
      await rejectJoinRequest(requestId);
      haptic("light");
      load();
    } catch {
      haptic("error");
      setActionError(t("team.errors.generic"));
    }
  }

  async function onRemove(userId, name) {
    if (!window.confirm(t("team.removeConfirm", { name }))) return;
    setActionError(null);
    try {
      await removeCompanyMember(userId);
      haptic("light");
      load();
    } catch {
      haptic("error");
      setActionError(t("team.errors.generic"));
    }
  }

  async function onTransfer(userId, name) {
    if (!window.confirm(t("team.transferConfirm", { name }))) return;
    setActionError(null);
    try {
      await transferCompanyOwnership(userId);
      haptic("success");
      load();
    } catch {
      haptic("error");
      setActionError(t("team.errors.generic"));
    }
  }

  if (state.loading) return <Spinner>{t("messages.loading")}</Spinner>;
  if (state.error) return <Msg type="error">{t("team.loadError")}</Msg>;

  const data = state.data;
  const isOwner = data.my_role === "owner";
  // 29.08.2026 (макет "18 · Компания — Команда", Untitled-22, выноска
  // "Шаг 20") — лимит НЕ отклоняет запрос автоматически, он просто ждёт
  // владельца (approve_join_request на бэкенде и так уже кидает
  // MEMBER_LIMIT_REACHED, не трогая сам запрос — см. guro_storage.py).
  // Раньше это было видно только ПОСЛЕ неудачного клика на "Принять"
  // (реактивная ошибка); теперь предупреждение показывается заранее, а
  // сама кнопка "Принять" сразу неактивна, как на макете.
  const atLimit = isOwner && data.member_count >= data.member_limit;

  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <div className="card">
        <div className="project-head">
          <h3>{t("team.title")}</h3>
          <span className="team-counter-badge">{t("team.counter", { count: data.member_count, limit: data.member_limit })}</span>
        </div>
        {isOwner && (
          <div className="workspace-switch" style={{ marginTop: 10 }}>
            <button type="button" className={tab === "requests" ? "is-active" : ""} onClick={() => setTab("requests")}>
              {t("team.tabRequests")}{data.requests?.length > 0 ? ` ${data.requests.length}` : ""}
            </button>
            <button type="button" className={tab === "members" ? "is-active" : ""} onClick={() => setTab("members")}>
              {t("team.tabMembers")} {data.member_count}
            </button>
          </div>
        )}
        {isOwner && typeof data.approvals_left_today === "number" && (
          <div className="partner-meta" style={{ marginTop: 6 }}>
            {t("team.approvalsLeftToday", { n: data.approvals_left_today })}
          </div>
        )}
      </div>

      <Msg type="error">{actionError}</Msg>

      {isOwner && tab === "requests" && (
        <>
          {(!data.requests || data.requests.length === 0) && (
            <div className="partner-meta">{t("team.requestsEmpty")}</div>
          )}
          {data.requests?.map((r) => (
            <div key={r.id} className="card">
              <div className="partner-name">
                {r.name || (r.username ? `@${r.username}` : t("common.noName"))}
                {r.position_text ? ` — ${r.position_text}` : ""}
              </div>
              <div className="partner-meta">{formatDate(r.created_at)}</div>
              <div className="recruiter-quick-actions" style={{ marginTop: 10 }}>
                <button type="button" className="btn" onClick={() => onApprove(r.id)} disabled={atLimit}>
                  {t("team.approveBtn")}
                </button>
                <button type="button" className="btn secondary" onClick={() => onReject(r.id)}>
                  {t("team.rejectBtn")}
                </button>
              </div>
            </div>
          ))}
          {atLimit && data.requests?.length > 0 && (
            <div className="mismatch-banner">
              ⚠️ {t("team.limitReachedBanner", { limit: data.member_limit, proLimit: 20 })}
            </div>
          )}
        </>
      )}

      {(tab === "members" || !isOwner) && data.members.map((m) => (
        <div key={m.user_id} className="card">
          <div className="partner-name">
            {m.name || (m.username ? `@${m.username}` : t("common.noName"))}
            <span className="recruiter-role-badge" style={{ marginLeft: 8 }}>
              {t(`team.role.${m.role}`)}
            </span>
          </div>
          {m.position_text && <div className="partner-meta">{m.position_text}</div>}
          {isOwner && m.role !== "owner" && (
            <div className="recruiter-quick-actions" style={{ marginTop: 10 }}>
              <button type="button" className="btn secondary" onClick={() => onRemove(m.user_id, m.name || m.username)}>
                {t("team.removeBtn")}
              </button>
              <button type="button" className="btn secondary" onClick={() => onTransfer(m.user_id, m.name || m.username)}>
                {t("team.transferBtn")}
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
