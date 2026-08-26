import { useEffect, useRef, useState } from "react";
import { getThread, sendMessage, ApiError } from "../../api.js";
import { Spinner, Msg } from "../Shared.jsx";
import { haptic } from "../../telegram.js";
import { useLang } from "../../i18n.jsx";

const ERROR_KEYS = {
  SUBSCRIPTION_REQUIRED: "thread.error.SUBSCRIPTION_REQUIRED",
  RATE_LIMITED: "thread.error.RATE_LIMITED",
  NO_RECIPIENT_PROFILE: "thread.error.NO_RECIPIENT_PROFILE",
  EMPTY_BODY: "thread.error.EMPTY_BODY",
};

// Переписка с ОДНИМ человеком (адресуется по его user_id, не по id треда —
// тред может ещё не существовать в БД, если сообщений ещё не было, см.
// GET /api/messages/with/<user_id> в guro_id_api.py).
export function ThreadScreen({ otherUserId, onBack, viaWorkspace }) {
  const { t } = useLang();
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState(null);
  const bottomRef = useRef(null);

  function load() {
    getThread(otherUserId)
      .then((data) => {
        setState({ loading: false, data, error: null });
        requestAnimationFrame(() => bottomRef.current?.scrollIntoView());
      })
      .catch((error) => setState({ loading: false, data: null, error }));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [otherUserId]);

  async function onSend(e) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setSending(true);
    setSendError(null);
    try {
      await sendMessage({ recipientId: otherUserId, body: text, viaWorkspace });
      setDraft("");
      haptic("light");
      load();
    } catch (error) {
      setSendError(error);
      haptic("error");
    } finally {
      setSending(false);
    }
  }

  if (state.loading) return <Spinner>{t("thread.loading")}</Spinner>;
  if (state.error) return <Msg type="error">{t("thread.loadError")}</Msg>;

  const { data } = state;
  const heading = data.other_name || (data.other_username ? `@${data.other_username}` : t("common.noName"));
  const errorText = sendError
    ? t((sendError instanceof ApiError && ERROR_KEYS[sendError.code]) || "thread.error.generic")
    : null;

  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.backToMessages")}
      </button>
      <div className="card">
        <h3>{heading}</h3>
        <div className="thread-messages">
          {data.messages.length === 0 && (
            <div className="partner-meta">
              {data.can_send_first ? t("thread.emptyCanSend") : t("thread.emptyCannotSend")}
            </div>
          )}
          {data.messages.map((m) => (
            <div key={m.id} className={`thread-bubble ${m.mine ? "mine" : "theirs"}`}>
              {m.body}
              {/* Метка кабинета-источника (2.7, ТЗ "Гуро рекрутер каб") —
                  только когда написано НЕ из личного профиля, чтобы не
                  засорять обычную переписку очевидным по умолчанию ярлыком. */}
              {m.via_workspace && m.via_workspace !== "personal" && (
                <div className="thread-bubble-source">
                  {t("thread.viaWorkspace", { workspace: t(`workspace.${m.via_workspace}`) })}
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        {(data.messages.length > 0 || data.can_send_first) && (
          <form onSubmit={onSend} className="thread-composer">
            <textarea
              rows={2}
              placeholder={t("thread.placeholder")}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={sending}
            />
            <button className="btn" type="submit" disabled={sending || !draft.trim()}>
              {sending ? t("thread.sending") : t("thread.send")}
            </button>
          </form>
        )}
        <Msg type="error">{errorText}</Msg>
      </div>
    </div>
  );
}
