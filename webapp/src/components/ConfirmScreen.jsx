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

const EMPTY_FORM = {
  confirmerUsername: "",
  vertical: "",
  geo: "",
  offer: "",
  amountReceived: "",
  amountPaid: "",
  review: "",
  amountVisible: false,
};

export function ConfirmScreen() {
  const [form, setForm] = useState(EMPTY_FORM);
  const [state, setState] = useState({ loading: false, ok: false, error: null });

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function onSubmit(e) {
    e.preventDefault();
    const q = form.confirmerUsername.trim().replace(/^@/, "");
    if (!q) return;
    setState({ loading: true, ok: false, error: null });
    try {
      await createPartnership({ ...form, confirmerUsername: q });
      setState({ loading: false, ok: true, error: null });
      setForm(EMPTY_FORM);
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
        профилях обоих только после его ответа. Офер и отзыв видны всем
        чужим (в этом и смысл — проверить репутацию контакта), суммы —
        только если включите показ ниже.
      </div>
      <form onSubmit={onSubmit}>
        <label>Юзернейм контрагента</label>
        <input
          type="text"
          placeholder="Юзернейм контрагента"
          value={form.confirmerUsername}
          onChange={(e) => set("confirmerUsername", e.target.value)}
        />
        <label>Вертикаль (необязательно)</label>
        <input
          type="text"
          placeholder="Вертикаль (необязательно)"
          value={form.vertical}
          onChange={(e) => set("vertical", e.target.value)}
        />
        <label>Гео (необязательно)</label>
        <input
          type="text"
          placeholder="Одесса, Кипр…"
          value={form.geo}
          onChange={(e) => set("geo", e.target.value)}
        />
        <label>Оффер — суть сделки (необязательно)</label>
        <input
          type="text"
          placeholder="Например: привёл байера на казино-трафик"
          value={form.offer}
          onChange={(e) => set("offer", e.target.value)}
        />
        <label>Сумма (необязательно)</label>
        <div className="amount-row">
          <input
            type="number"
            inputMode="decimal"
            placeholder="Я получил, $"
            value={form.amountReceived}
            onChange={(e) => set("amountReceived", e.target.value)}
          />
          <input
            type="number"
            inputMode="decimal"
            placeholder="Я заплатил, $"
            value={form.amountPaid}
            onChange={(e) => set("amountPaid", e.target.value)}
          />
        </div>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.amountVisible}
            onChange={(e) => set("amountVisible", e.target.checked)}
          />
          Показывать сумму чужим (по умолчанию скрыта)
        </label>
        <label>Отзыв — ваше сообщение о партнёрстве (необязательно)</label>
        <textarea
          rows={3}
          placeholder="Как прошло сотрудничество"
          value={form.review}
          onChange={(e) => set("review", e.target.value)}
        />
        <button className="btn" type="submit" disabled={state.loading || !form.confirmerUsername.trim()}>
          {state.loading ? "Отправляем…" : "Отправить на подтверждение"}
        </button>
      </form>
      <Msg type="error">{errorText}</Msg>
      <Msg type="ok">{state.ok ? "Заявка отправлена. Ждём подтверждения от контрагента." : null}</Msg>
    </div>
  );
}
