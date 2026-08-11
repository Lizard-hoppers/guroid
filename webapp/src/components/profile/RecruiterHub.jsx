import { EditableField } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { setRecruiterProfileField, setRecruiterPrivacyField } from "../../api.js";
import { SubscribeScreen } from "../SubscribeScreen.jsx";

// Поля витрины рекрутера (Фаза 3, 12.08.2026) — все редактируются прямо
// тут, в отличие от личного профиля, у них нет анкеты-источника вообще
// (см. guro_constants.RECRUITER_EXTRA_FIELDS).
const FIELD_DEFS = [
  { field: "name", label: "Имя / подпись", placeholder: "Например: Иван Петров, HR отдел" },
  { field: "company", label: "Компания", placeholder: "Название компании" },
  { field: "vertical", label: "Вертикаль", placeholder: "Gambling, Crypto…" },
  { field: "profession", label: "Должность", placeholder: "HR Manager, Talent Lead…" },
  { field: "cv_text", label: "О себе / агентстве", placeholder: "Кого и как вы нанимаете", multiline: true },
  { field: "website", label: "Сайт", placeholder: "example.com" },
  { field: "offering", label: "Чем полезен", placeholder: "Какие вакансии/услуги предлагаете", multiline: true },
];

const PRIVACY_FIELDS = [
  "show_name", "show_company", "show_vertical", "show_profession", "show_cv", "show_contacts", "show_offers",
];

// Уточнённые подписи под витрину рекрутера — та же PRIVACY_LABELS база
// личного профиля упоминает LinkedIn/"ищу", которых тут нет.
const RECRUITER_PRIVACY_LABELS = {
  show_name: "Имя / подпись",
  show_company: "Компания",
  show_vertical: "Вертикаль",
  show_profession: "Должность",
  show_cv: "О себе / агентстве",
  show_contacts: "Сайт",
  show_offers: "Чем полезен",
};

// Кабинет рекрутера — отдельная витрина поверх личного профиля (см. план
// 11.08.2026): общий рейтинг/партнёрства, но своя оплата и свои поля.
// Без активной подписки рекрутера показываем апсейл вместо редактора.
export function RecruiterHub({ data, onFieldSaved, onPrivacyChange, onSubscribed }) {
  if (!data.is_recruiter_subscribed) {
    return (
      <div>
        <div className="card">
          <h3>Кабинет рекрутера</h3>
          <p className="partner-meta">
            Отдельная витрина поверх личного профиля — своё имя, компания и CV для рабочего
            режима, независимо от того, что видно в личном профиле. Рейтинг и история сделок
            остаются общими для обоих режимов.
          </p>
        </div>
        <SubscribeScreen product="recruiter" onSubscribed={onSubscribed} />
      </div>
    );
  }

  return (
    <div>
      <div className="card">
        <h3>Кабинет рекрутера</h3>
        {FIELD_DEFS.map((f) => (
          <EditableField
            key={f.field}
            field={f.field}
            label={f.label}
            placeholder={f.placeholder}
            multiline={f.multiline}
            value={data[f.field]}
            onSaved={(v) => onFieldSaved(f.field, v)}
            saveField={setRecruiterProfileField}
          />
        ))}
      </div>
      <PrivacyToggles
        privacy={data.privacy}
        onChange={onPrivacyChange}
        fields={PRIVACY_FIELDS}
        savePrivacyField={setRecruiterPrivacyField}
        labels={RECRUITER_PRIVACY_LABELS}
        hint="Управляет тем, что видят чужие в кабинете рекрутера (независимо от тумблеров личного профиля). По умолчанию скрыто — включите то, что хотите показать."
      />
    </div>
  );
}
