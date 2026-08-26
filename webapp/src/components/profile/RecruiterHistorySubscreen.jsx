import { PartnersList } from "../Shared.jsx";
import { useLang } from "../../i18n.jsx";

// "История наймов" (ТЗ "Гуро рекрутер каб", раздел 4 — переименование
// "История партнёрств" -> "История наймов" в контексте кабинета Рекрутер).
// Переиспользует ОБЩИЙ список партнёрств личного профиля (раздел 3 ТЗ:
// баллы за найм пишутся в общий W, отдельного хранилища нет), просто
// фильтрует по ptype="hire" — та же история, что видна и в личном
// профиле, тут показана только её рабочая часть.
export function RecruiterHistorySubscreen({ partners, onBack }) {
  const { t } = useLang();
  const hires = (partners || []).filter((p) => p.ptype === "hire");
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <div className="card">
        <h3>{t("recruiter.history.title")}</h3>
        <PartnersList partners={hires} emptyHint={t("recruiter.history.empty")} allowRating />
      </div>
    </div>
  );
}
