import { useState } from "react";
import { setPrivacyField } from "../api.js";
import { haptic } from "../telegram.js";
import { Msg } from "./Shared.jsx";

// Полный словарь подписей — каждый экран передаёт СВОЙ подмножество полей
// через проп `fields` (например, только show_cv на экране CV), а не весь
// список сразу. Opt-in: по умолчанию всё выключено (скрыто), человек сам
// включает то, что хочет показать — см. guro_constants.PRIVACY_FIELDS.
export const PRIVACY_LABELS = {
  show_name: "Имя",
  show_company: "Компания",
  show_vertical: "Вертикаль / специализация",
  show_profession: "Должность",
  show_tenure: "Стаж в комьюнити",
  show_reputation: "Рейтинг",
  show_cv: "CV",
  show_contacts: "Контакты (LinkedIn, сайт)",
  show_offers: "Офферы (ищу / полезен)",
};

// savePrivacyField/labels (Фаза 3, 12.08.2026) — по умолчанию личный
// профиль (setPrivacyField/PRIVACY_LABELS), RecruiterHub передаёт свои
// (setRecruiterPrivacyField + уточнённые подписи — у витрины рекрутера
// нет LinkedIn/"ищу", только сайт/"полезен").
export function PrivacyToggles({
  privacy, onChange, fields, hint, savePrivacyField = setPrivacyField, labels = PRIVACY_LABELS,
}) {
  const [pending, setPending] = useState(null);
  const [error, setError] = useState("");

  async function toggle(key) {
    const prev = privacy[key];
    const next = !prev;
    setPending(key);
    setError("");
    onChange({ ...privacy, [key]: next }); // оптимистичное обновление
    try {
      const updated = await savePrivacyField(key, next);
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
      {hint && <div className="privacy-hint">{hint}</div>}
      {fields.map((key) => (
        <div className="privacy-row" key={key}>
          <div>
            <div className="privacy-row-label">{labels[key]}</div>
            <div className="privacy-row-note">
              {privacy[key] ? "Видно всем в поиске" : "Скрыто от чужого поиска"}
            </div>
          </div>
          <label className="switch">
            <input
              type="checkbox"
              checked={!!privacy[key]}
              disabled={pending === key}
              onChange={() => toggle(key)}
            />
            <span className="slider" />
          </label>
        </div>
      ))}
      <Msg type="error">{error}</Msg>
    </div>
  );
}
