import { useState } from "react";
import { setPrivacyField } from "../api.js";
import { haptic } from "../telegram.js";
import { Msg } from "./Shared.jsx";

const FIELDS = [
  { key: "show_name", label: "Имя" },
  { key: "show_company", label: "Компания" },
  { key: "show_vertical", label: "Вертикаль / специализация" },
  { key: "show_tenure", label: "Стаж в комьюнити" },
  { key: "show_reputation", label: "Рейтинг" },
];

// Opt-in: по умолчанию всё выключено (скрыто), человек сам включает то,
// что хочет показать. Партнёрства и username сюда намеренно не входят —
// они видны всегда, см. guro_constants.PRIVACY_FIELDS на бэкенде.
export function PrivacyToggles({ privacy, onChange }) {
  const [pending, setPending] = useState(null);
  const [error, setError] = useState("");

  async function toggle(key) {
    const prev = privacy[key];
    const next = !prev;
    setPending(key);
    setError("");
    onChange({ ...privacy, [key]: next }); // оптимистичное обновление
    try {
      const updated = await setPrivacyField(key, next);
      onChange(updated);
      haptic("select");
    } catch {
      onChange({ ...privacy, [key]: prev }); // откат при ошибке
      setError("Не получилось сохранить настройку. Попробуйте ещё раз.");
      haptic("error");
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="card">
      <h3>Приватность</h3>
      <div className="privacy-hint">
        По умолчанию ничего не видно чужим, кроме факта участия в GURO ID и
        партнёрств. Включите тумблер — и поле появится в вашей карточке для
        тех, кто ищет вас. Партнёрства (с кем сотрудничали) видны всегда —
        в этом и есть смысл GURO ID.
      </div>
      {FIELDS.map((f) => (
        <div className="privacy-row" key={f.key}>
          <div>
            <div className="privacy-row-label">{f.label}</div>
            <div className="privacy-row-note">
              {privacy[f.key] ? "Видно всем в поиске" : "Скрыто от чужого поиска"}
            </div>
          </div>
          <label className="switch">
            <input
              type="checkbox"
              checked={!!privacy[f.key]}
              disabled={pending === f.key}
              onChange={() => toggle(f.key)}
            />
            <span className="slider" />
          </label>
        </div>
      ))}
      <Msg type="error">{error}</Msg>
    </div>
  );
}
