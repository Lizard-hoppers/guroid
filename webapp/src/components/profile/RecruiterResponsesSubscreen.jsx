import { useLang } from "../../i18n.jsx";

// "Отклики" (ТЗ "Гуро рекрутер каб", раздел 2.7) — заглушка: структурная
// механика откликов на вакансии (кнопка "Откликнуться" на вакансии, поток
// заявок кандидатов) прорабатывается отдельно вместе с разделом
// "Вакансии" (см. ТЗ, раздел 5, "вне рамок этого ТЗ"). Пока нет данных,
// которые можно было бы тут показать — честный пустой экран, а не
// притворяться, что фича готова.
export function RecruiterResponsesSubscreen({ onBack }) {
  const { t } = useLang();
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <div className="card">
        <h3>{t("recruiter.responses.title")}</h3>
        <p className="partner-meta">{t("recruiter.responses.comingSoon")}</p>
      </div>
    </div>
  );
}
