import { useState } from "react";
import { setPrivacyField } from "../api.js";
import { haptic } from "../telegram.js";
import { Msg } from "./Shared.jsx";

const FIELDS = [
  { key: "hide_name", label: "Имя" },
  { key: "hide_company", label: "Компания" },
  { key: "hide_vertical", label: "Вертикаль / специализация" },
  { key: "hide_tenure", label: "Стаж в комьюнити" },
  { key: "hide_reputation", label: "Рейтинг" },
];

// Партнёрства и username сюда намеренно не входят — их скрыть нельзя,
// см. guro_constants.PRIVACY_FIELDS на бэкенде.
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
        По умолчанию всё видно. Включите тумблер — и поле исчезнет из вашей
        карточки для тех, кто ищет вас в GURO ID. Партнёрства (с кем
        сотрудничали) скрыть нельзя — в этом и есть смысл GURO ID.
      </div>
      {FIELDS.map((f) => (
        <div className="privacy-row" key={f.key}>
          <div>
            <div className="privacy-row-label">{f.label}</div>
            <div className="privacy-row-note">
              {privacy[f.key] ? "Скрыто от чужого поиска" : "Видно всем в поиске"}
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
