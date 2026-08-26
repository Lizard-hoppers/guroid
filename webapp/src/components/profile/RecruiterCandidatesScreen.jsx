import { useState } from "react";
import { browseResumes, browseVertical, searchByUserId } from "../../api.js";
import { DirectoryRow } from "../SearchScreen.jsx";
import { Msg, MetricsRow, IdentityLine, WorkStatusBadge, Spinner, CharacteristicButton } from "../Shared.jsx";
import { useLang } from "../../i18n.jsx";

// Канонические вертикали — те же, что и в SearchScreen.jsx личного профиля.
const VERTICALS = ["Gambling", "Betting", "Crypto", "Dating", "E-Commerce", "FinTech", "Nutra", "Other"];

// "Найти кандидата" (ТЗ "Гуро рекрутер каб", 2.6/раздел 5 — сама механика
// поиска по фильтрам вынесена в отдельную будущую итерацию, тут —
// минимально рабочая версия для главного экрана: переиспользует УЖЕ
// существующий browse по вертикали/резюме (тот же API, что у личного
// профиля, см. guro_id_api._resume_browse/_directory_browse), доступ
// теперь даёт ЛЮБАЯ активная подписка (личная/рекрутер/компания), не
// только личная — см. any_subscription_active в guro_id_api.py).
export function RecruiterCandidatesScreen({ onBack, onWrite }) {
  const { t } = useLang();
  const [state, setState] = useState({ loading: false, data: null, error: null });
  const [selected, setSelected] = useState(null); // открытая карточка кандидата

  async function runBrowse(kind, value) {
    setState({ loading: true, data: null, error: null });
    try {
      const data = kind === "resumes" ? await browseResumes(value) : await browseVertical(value);
      setState({ loading: false, data, error: null });
    } catch (error) {
      setState({ loading: false, data: null, error });
    }
  }

  async function openCandidate(userId) {
    setSelected({ loading: true, data: null });
    try {
      const data = await searchByUserId(userId);
      setSelected({ loading: false, data });
    } catch {
      setSelected(null);
    }
  }

  if (selected) {
    const p = selected.data;
    return (
      <div>
        <button type="button" className="subscreen-back" onClick={() => setSelected(null)}>
          {t("common.back")}
        </button>
        {selected.loading && <Spinner>{t("search.submitting")}</Spinner>}
        {p && (
          <div className="card">
            <h2 className={p.name === null ? "hidden-value" : ""}>
              {p.name === null ? t("common.hidden") : p.name || (p.username ? `@${p.username}` : t("common.noName"))}
            </h2>
            <WorkStatusBadge status={p.work_status} />
            <IdentityLine label={t("identity.vertical")} value={p.vertical} />
            <IdentityLine label={t("identity.company")} value={p.company} />
            <MetricsRow reputation={p.reputation_score} partnerships={p.confirmed_partnerships} daysInCommunity={p.days_in_community} />
            {onWrite && !p.locked && (
              <button type="button" className="btn secondary" style={{ marginTop: 12 }} onClick={() => onWrite(p.user_id)}>
                {t("messageBtn")}
              </button>
            )}
            {!p.locked && <CharacteristicButton profile={p} />}
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <div className="card">
        <h3>{t("recruiter.candidates.title")}</h3>
        <p className="partner-meta">{t("recruiter.candidates.hint")}</p>
        <div className="vertical-chips">
          {VERTICALS.map((v) => (
            <button key={v} type="button" className="vertical-chip" onClick={() => runBrowse("vertical", v)}>
              {v}
            </button>
          ))}
        </div>
        <button type="button" className="btn secondary" style={{ marginTop: 10 }} onClick={() => runBrowse("resumes")}>
          {t("recruiter.candidates.showAllResumes")}
        </button>
      </div>

      {state.loading && <Spinner>{t("search.submitting")}</Spinner>}
      {state.error && <Msg type="error">{t("search.genericError")}</Msg>}
      {state.data && state.data.results.length === 0 && (
        <div className="partner-meta">{t("search.emptyList")}</div>
      )}
      {state.data && state.data.results.length > 0 && (
        <div className="directory-results">
          {state.data.results.map((r) => (
            <DirectoryRow key={r.user_id} r={r} onOpen={openCandidate} />
          ))}
        </div>
      )}
    </div>
  );
}
