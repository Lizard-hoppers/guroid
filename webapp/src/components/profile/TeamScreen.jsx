import { useEffect, useState } from "react";
import {
  getCompanyTeam, approveJoinRequest, rejectJoinRequest, removeCompanyMember, transferCompanyOwnership, ApiError,
} from "../../api.js";
import { Msg, Spinner } from "../Shared.jsx";
import { useLang } from "../../i18n.jsx";
import { IconWarning } from "../Icons.jsx";
import { haptic } from "../../telegram.js";
import { formatDate, initialOf } from "../../utils.js";

// Экран "Команда" (ТЗ "Роли и управление командой", раздел 3.2, 27.08.2026)
// — таб "Запросы" (только Владельцу, сервер сам не отдаёт requests не-
// владельцу) + таб "Участники" (видно всем). Управляющие кнопки
// (Принять/Отклонить/Удалить/Передать владение) скрыты для Админа —
// он видит ровно то же самое, просто без кнопок (раздел 2 ТЗ: Админ не
// управляет составом команды).
export function TeamScreen({ onBack }) {
  const { t } = useLang();
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [actionError, setActionError] = useState(null);
  // Вкладка экрана (эталонный экран 18). Открываемся на «Запросах»:
  // владелец заходит сюда прежде всего разбирать заявки.
  const [tab, setTab] = useState("requests");

  function load() {
    setState((s) => ({ ...s, loading: true, error: null }));
    getCompanyTeam()
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((error) => setState({ loading: false, data: null, error }));
  }

  useEffect(load, []);

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

  const pendingCount = data.requests ? data.requests.length : 0;

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
        {isOwner && typeof data.approvals_left_today === "number" && (
          <div className="partner-meta" style={{ marginTop: 6 }}>
            {t("team.approvalsLeftToday", { n: data.approvals_left_today })}
          </div>
        )}
      </div>

      <Msg type="error">{actionError}</Msg>

      {/* Вкладки, а не две секции стопкой (эталонный экран 18 и ТЗ «Роли и
          команда», раздел 3.2). «Запросы» — только владельцу: участник
          заявки не одобряет, и вкладка ему пустует без смысла. */}
      {isOwner && (
        <div className="team-tabs">
          <button
            type="button"
            className={`team-tab${tab === "requests" ? " is-active" : ""}`}
            onClick={() => setTab("requests")}
          >
            {t("team.requestsTitle")}
            {pendingCount > 0 && <span className="chip">{pendingCount}</span>}
          </button>
          <button
            type="button"
            className={`team-tab${tab === "members" ? " is-active" : ""}`}
            onClick={() => setTab("members")}
          >
            {t("team.membersTitle")}
            <span className="chip">{data.member_count}</span>
          </button>
        </div>
      )}

      {isOwner && tab === "requests" && (
        <div className="card">
          <h3>{t("team.requestsTitle")}</h3>
          {(!data.requests || data.requests.length === 0) && (
            <div className="partner-meta">{t("team.requestsEmpty")}</div>
          )}
          {data.requests?.map((r) => (
            <div key={r.id} className="card">
              <div className="team-member-row">
                <div className="avatar-dot">{initialOf(r.name, r.username)}</div>
                <div className="team-member-main">
                  <div className="partner-name">
                    {r.name || (r.username ? `@${r.username}` : t("common.noName"))}
                  </div>
                  <div className="partner-meta">
                    {r.position_text ? `${r.position_text} · ` : ""}
                    {formatDate(r.created_at)}
                  </div>
                  <div className="recruiter-quick-actions" style={{ marginTop: 10 }}>
                    <button
                      type="button"
                      className="btn secondary accent-lime"
                      onClick={() => onApprove(r.id)}
                      disabled={atLimit}
                    >
                      {t("team.approveBtn")}
                    </button>
                    <button type="button" className="btn secondary" onClick={() => onReject(r.id)}>
                      {t("team.rejectBtn")}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
          {atLimit && data.requests?.length > 0 && (
            <div className="mismatch-banner">
              <IconWarning style={{ color: "var(--amber)" }} />{" "}
          {t("team.limitReachedBanner", { limit: data.member_limit, proLimit: 20 })}
            </div>
          )}
        </div>
      )}

      {(!isOwner || tab === "members") && (
      <div className="card">
        <h3>
          {t("team.membersTitle")}
          {" · "}
          {t("team.membersCounter", { count: data.member_count, limit: data.member_limit })}
        </h3>
        {data.members.map((m) => (
          <div key={m.user_id} className="card">
            <div className="team-member-row">
              <div className="avatar-dot">{initialOf(m.name, m.username)}</div>
              <div className="team-member-main">
                <div className="partner-name">
                  {m.name || (m.username ? `@${m.username}` : t("common.noName"))}
                  {/* 29.08.2026, регресс: .recruiter-role-badge —
                      position:absolute (задуман под наложение на аватар в
                      RecruiterHub), тут ломал вёрстку. .role-badge — та же
                      пилюля, но в потоке документа. */}
                  <span
                    className={`role-badge${m.role === "owner" ? " role-badge--owner" : ""}`}
                    style={{ marginLeft: 8 }}
                  >
                    {t(`team.role.${m.role}`)}
                  </span>
                </div>
                {m.position_text && <div className="partner-meta">{m.position_text}</div>}
                {data.my_user_id === m.user_id && (
                  <span className="role-badge role-badge--you">{t("team.isYou")}</span>
                )}
                {isOwner && m.role !== "owner" && (
                  <div className="recruiter-quick-actions" style={{ marginTop: 10 }}>
                    <button type="button" className="btn secondary" onClick={() => onRemove(m.user_id, m.name || m.username)}>
                      {t("team.removeBtn")}
                    </button>
                    <button
                      type="button"
                      className="btn secondary accent-cyan"
                      onClick={() => onTransfer(m.user_id, m.name || m.username)}
                    >
                      {t("team.transferBtn")}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      )}

      {/* Пояснение из эталонного экрана 18. ТЗ называет это принципиально
          важным: ролей всего две, и реальная должность человека прав не
          добавляет — иначе непонятно, почему у аффилейт-менеджера и HR
          одинаковые возможности. */}
      <div className="card">
        <h3>{t("team.rolesTitle")}</h3>
        <div className="privacy-hint">{t("team.rolesOwner")}</div>
        <div className="privacy-hint" style={{ marginBottom: 0 }}>
          {t("team.rolesAdmin")}
        </div>
      </div>
    </div>
  );
}
