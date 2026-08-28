import { useState } from "react";
import { setPrivacyField } from "../api.js";
import { haptic } from "../telegram.js";
import { Msg } from "./Shared.jsx";
import { useLang } from "../i18n.jsx";

// Полный словарь ключей перевода — каждый экран передаёт СВОЙ подмножество
// полей через проп `fields` (например, только show_cv на экране CV), а не
// весь список сразу. Opt-in: по умолчанию всё выключено (скрыто), человек
// сам включает то, что хочет показать — см. guro_constants.PRIVACY_FIELDS.
export const PRIVACY_LABELS = {
  show_name: "privacy.label.show_name",
  show_company: "privacy.label.show_company",
  show_vertical: "privacy.label.show_vertical",
  show_profession: "privacy.label.show_profession",
  show_tenure: "privacy.label.show_tenure",
  show_reputation: "privacy.label.show_reputation",
  show_cv: "privacy.label.show_cv",
  show_contacts: "privacy.label.show_contacts",
  show_offers: "privacy.label.show_offers",
};

// savePrivacyField/labels (Фаза 3, 12.08.2026) — по умолчанию личный
// профиль (setPrivacyField/PRIVACY_LABELS), RecruiterHub передаёт свои
// (setRecruiterPrivacyField + уточнённые ключи — у витрины рекрутера
// нет LinkedIn/"ищу", только сайт/"полезен"). labels — словарь key ->
// ключ перевода (не сам текст), т.к. язык может переключиться в рантайме.
// title/children (28.08.2026, экран "Приватность профиля",
// PrivacySubscreen.jsx) — необязательные, чтобы не трогать 5 уже
// существующих вызовов (CV/Contacts/Offers/RecruiterHub/CompanyHub), у
// тех остаётся дефолтный заголовок "Приватность" и никакого футера.
export function PrivacyToggles({
  privacy, onChange, fields, hint, savePrivacyField = setPrivacyField, labels = PRIVACY_LABELS,
  title, children,
}) {
  const { t } = useLang();
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
      setError(t("privacy.saveError"));
      haptic("error");
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="card">
      <h3>{title || t("privacy.title")}</h3>
      {hint && <div className="privacy-hint">{hint}</div>}
      {fields.map((key) => (
        <div className="privacy-row" key={key}>
          <div>
            <div className="privacy-row-label">{t(labels[key])}</div>
            <div className="privacy-row-note">
              {privacy[key] ? t("privacy.visible") : t("privacy.hidden")}
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
      {children}
      <Msg type="error">{error}</Msg>
    </div>
  );
}
