import { useEffect, useRef, useState } from "react";
import { getThread, sendMessage, ApiError } from "../../api.js";
import { Spinner, Msg } from "../Shared.jsx";
import { haptic } from "../../telegram.js";

const ERROR_MESSAGES = {
  SUBSCRIPTION_REQUIRED:
    "Чтобы написать первым, нужна активная подписка GURO ID — вы уже видели полный профиль " +
    "этого человека, если общаетесь впервые.",
  RATE_LIMITED: "Слишком много новых переписок за сегодня. Попробуйте завтра.",
  NO_RECIPIENT_PROFILE: "Этот пользователь ещё не проходил анкету бота.",
  EMPTY_BODY: "Сообщение не может быть пустым.",
};

// Переписка с ОДНИМ человеком (адресуется по его user_id, не по id треда —
// тред может ещё не существовать в БД, если сообщений ещё не было, см.
// GET /api/messages/with/<user_id> в guro_id_api.py).
export function ThreadScreen({ otherUserId, onBack }) {
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
      await sendMessage({ recipientId: otherUserId, body: text });
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

  if (state.loading) return <Spinner>Загружаем переписку…</Spinner>;
  if (state.error) return <Msg type="error">Не удалось открыть переписку.</Msg>;

  const { data } = state;
  const heading = data.other_name || (data.other_username ? `@${data.other_username}` : "Без имени");
  const errorText = sendError
    ? (sendError instanceof ApiError && ERROR_MESSAGES[sendError.code]) || "Не получилось отправить сообщение."
    : null;

  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        ‹ Сообщения
      </button>
      <div className="card">
        <h3>{heading}</h3>
        <div className="thread-messages">
          {data.messages.length === 0 && (
            <div className="partner-meta">
              {data.can_send_first
                ? "Переписки пока нет — напишите первое сообщение."
                : "Написать первым можно только тем, чей профиль вы открыли по подписке GURO ID."}
            </div>
          )}
          {data.messages.map((m) => (
            <div key={m.id} className={`thread-bubble ${m.mine ? "mine" : "theirs"}`}>
              {m.body}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        {(data.messages.length > 0 || data.can_send_first) && (
          <form onSubmit={onSend} className="thread-composer">
            <textarea
              rows={2}
              placeholder="Сообщение…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={sending}
            />
            <button className="btn" type="submit" disabled={sending || !draft.trim()}>
              {sending ? "Отправляем…" : "Отправить"}
            </button>
          </form>
        )}
        <Msg type="error">{errorText}</Msg>
      </div>
    </div>
  );
}
