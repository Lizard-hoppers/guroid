import { useState } from "react";
import { createPartnership, ApiError } from "../api.js";
import { Msg } from "./Shared.jsx";
import { haptic } from "../telegram.js";

const ERROR_MESSAGES = {
  SELF_PARTNERSHIP: "Нельзя подтвердить партнёрство с самим собой.",
  RATE_LIMITED: "Заявка с этим человеком уже отправлялась за последние 24 часа.",
  NO_CONFIRMER_PROFILE:
    "Этот пользователь ещё не проходил анкету @GamblingCommunitybot — бот не может ему написать.",
};

export function ConfirmScreen() {
  const [confirmerUsername, setConfirmerUsername] = useState("");
  const [vertical, setVertical] = useState("");
  const [geo, setGeo] = useState("");
  const [state, setState] = useState({ loading: false, ok: false, error: null });

  async function onSubmit(e) {
    e.preventDefault();
    const q = confirmerUsername.trim().replace(/^@/, "");
    if (!q) return;
    setState({ loading: true, ok: false, error: null });
    try {
      await createPartnership({ confirmerUsername: q, vertical, geo });
      setState({ loading: false, ok: true, error: null });
      setConfirmerUsername("");
      setVertical("");
      setGeo("");
      haptic("success");
    } catch (error) {
      setState({ loading: false, ok: false, error });
      haptic("error");
    }
  }

  const errorText = state.error
    ? (state.error instanceof ApiError && ERROR_MESSAGES[state.error.code]) ||
      "Не получилось отправить заявку."
    : null;

  return (
    <div className="card">
      <h3>Подтвердить партнёрство</h3>
      <div className="privacy-hint">
        Укажите юзернейм человека, с которым уже состоялось сотрудничество.
        Ему придёт запрос на подтверждение от бота — запись появится в
        профилях обоих только после его ответа.
      </div>
      <form onSubmit={onSubmit}>
        <label>Юзернейм контрагента</label>
        <input
          type="text"
          placeholder="Юзернейм контрагента"
          value={confirmerUsername}
          onChange={(e) => setConfirmerUsername(e.target.value)}
        />
        <label>Вертикаль (необязательно)</label>
        <input
          type="text"
          placeholder="Вертикаль (необязательно)"
          value={vertical}
          onChange={(e) => setVertical(e.target.value)}
        />
        <label>Гео (необязательно)</label>
        <input
          type="text"
          placeholder="Одесса, Кипр…"
          value={geo}
          onChange={(e) => setGeo(e.target.value)}
        />
        <button className="btn" type="submit" disabled={state.loading || !confirmerUsername.trim()}>
          {state.loading ? "Отправляем…" : "Отправить на подтверждение"}
        </button>
      </form>
      <Msg type="error">{errorText}</Msg>
      <Msg type="ok">{state.ok ? "Заявка отправлена. Ждём подтверждения от контрагента." : null}</Msg>
    </div>
  );
}
