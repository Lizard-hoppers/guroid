import { useEffect, useState } from "react";
import { getMessages } from "../../api.js";
import { Spinner, Msg } from "../Shared.jsx";
import { ThreadScreen } from "./ThreadScreen.jsx";
import { useLang } from "../../i18n.jsx";

// Список переписок + сама переписка (ThreadScreen) — оба под одним пунктом
// меню профиля "Мои сообщения". initialThreadUserId — заход сразу в
// конкретную переписку (кнопка "Написать" в поиске или deep-link из
// уведомления бота ?thread=<id>, см. App.jsx), consumед сразу при монтировании,
// чтобы повторный заход на вкладку "Профиль" не открывал её заново.
export function MessagesScreen({ initialThreadUserId, onConsumeInitialThread, onBack }) {
  const { t } = useLang();
  const [activeUserId, setActiveUserId] = useState(
    initialThreadUserId != null ? Number(initialThreadUserId) : null,
  );
  const [state, setState] = useState({ loading: true, threads: null, error: null });

  useEffect(() => {
    if (initialThreadUserId != null) onConsumeInitialThread?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (activeUserId != null) return;
    setState({ loading: true, threads: null, error: null });
    getMessages()
      .then(({ threads }) => setState({ loading: false, threads, error: null }))
      .catch((error) => setState({ loading: false, threads: null, error }));
  }, [activeUserId]);

  if (activeUserId != null) {
    return <ThreadScreen otherUserId={activeUserId} onBack={() => setActiveUserId(null)} />;
  }

  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <div className="card">
        <h3>{t("messages.title")}</h3>
        {state.loading && <Spinner>{t("messages.loading")}</Spinner>}
        {state.error && <Msg type="error">{t("messages.loadError")}</Msg>}
        {state.threads && state.threads.length === 0 && (
          <div className="partner-meta">{t("messages.empty")}</div>
        )}
        {state.threads?.map((th) => {
          const heading = th.other_name || (th.other_username ? `@${th.other_username}` : t("common.noName"));
          return (
            <button
              key={th.other_user_id}
              type="button"
              className="thread-row"
              onClick={() => setActiveUserId(th.other_user_id)}
            >
              <div className="thread-row-main">
                <div className="thread-row-name">
                  {heading}
                  {th.unread_count > 0 && <span className="thread-unread-dot" />}
                </div>
                <div className="partner-meta thread-row-preview">{th.last_message}</div>
              </div>
              <span className="profile-menu-item-chevron">›</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
