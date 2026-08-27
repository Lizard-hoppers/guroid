import { useState } from "react";
import { search, searchCandidates, searchByUserId, ApiError } from "../../api.js";
import { DirectoryRow } from "../SearchScreen.jsx";
import { usePositions } from "../VacanciesScreen.jsx";
import { Msg, MetricsRow, IdentityLine, WorkStatusBadge, Spinner, CharacteristicButton } from "../Shared.jsx";
import { useLang } from "../../i18n.jsx";
import { formatDate } from "../../utils.js";

// Канонические вертикали — те же, что и в SearchScreen.jsx личного профиля.
const VERTICALS = ["Gambling", "Betting", "Crypto", "Dating", "E-Commerce", "FinTech", "Nutra", "Other"];

// "Найти кандидата" (ТЗ "Гуро рекрутер каб", 2.6 → полностью переписано
// 27.08.2026 под "экраны по ТЗ от 23.08", "Поиск кандидатов") — полный
// фильтр: вертикаль + грейд + должность (тот же справочник /api/positions,
// что и у формы публикации вакансии, см. VacanciesScreen.usePositions) +
// "Только те, кто ищет работу" (work_status=looking) + "Сначала высокий
// рейтинг" (top=1). Грейд/должность матчатся ПОДСТРОКОЙ по свободнотекстовым
// profession/cv_profession (у личного профиля нет структурированной
// таксономии грейда вакансий — cv_grade использует ДРУГОЙ список меток, см.
// CV_GRADE_LEVELS в guro_constants.py), см. _grade_position_ok в guro_id_api.py.
export function RecruiterCandidatesScreen({ onBack, onWrite }) {
  const { t } = useLang();
  const positions = usePositions();
  const [username, setUsername] = useState("");
  const [vertical, setVertical] = useState("");
  const [grade, setGrade] = useState("");
  const [position, setPosition] = useState("");
  const [lookingOnly, setLookingOnly] = useState(false);
  const [topRating, setTopRating] = useState(false);
  const [state, setState] = useState({ loading: false, data: null, error: null });
  const [selected, setSelected] = useState(null); // открытая карточка кандидата

  const positionOptions = vertical && grade ? (positions.professions[vertical]?.[grade] || []) : [];

  async function runFilterSearch() {
    setState({ loading: true, data: null, error: null });
    try {
      const data = await searchCandidates({ vertical, grade, position, looking: lookingOnly, top: topRating });
      setState({ loading: false, data, error: null });
    } catch (error) {
      setState({ loading: false, data: null, error });
    }
  }

  async function runUsernameSearch(e) {
    e.preventDefault();
    if (!username.trim()) return;
    setState({ loading: true, data: null, error: null });
    try {
      const data = await search(username.trim());
      setState({ loading: false, data, error: null });
    } catch (error) {
      setState({
        loading: false, data: null,
        error: error instanceof ApiError && error.code === "NOT_FOUND" ? "notFound" : error,
      });
    }
  }

  async function openCandidate(userId) {
    setSelected({ loading: true, data: null, error: null });
    try {
      const data = await searchByUserId(userId);
      setSelected({ loading: false, data, error: null });
    } catch (error) {
      setSelected({
        loading: false, data: null,
        error: error instanceof ApiError && error.code === "VIEW_LIMIT_REACHED"
          ? t("search.viewLimitReached", { date: formatDate(error.details?.resets_at) })
          : t("search.genericError"),
      });
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
        {selected.error && <Msg type="error">{selected.error}</Msg>}
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

        <form onSubmit={runUsernameSearch}>
          <label>{t("recruiter.candidates.usernameLabel")}</label>
          <input
            type="text"
            placeholder={t("recruiter.candidates.usernamePlaceholder")}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <button type="submit" className="btn secondary" style={{ marginTop: 8 }} disabled={!username.trim()}>
            {t("recruiter.candidates.usernameSubmit")}
          </button>
        </form>

        <label style={{ marginTop: 14 }}>{t("recruiter.candidates.verticalLabel")}</label>
        <div className="vertical-chips">
          {VERTICALS.map((v) => (
            <button
              key={v}
              type="button"
              className={`vertical-chip${vertical === v ? " is-selected" : ""}`}
              onClick={() => {
                setVertical(vertical === v ? "" : v);
                setGrade("");
                setPosition("");
              }}
            >
              {v}
            </button>
          ))}
        </div>

        <label style={{ marginTop: 10 }}>{t("recruiter.candidates.gradeLabel")}</label>
        <div className="vertical-chips">
          {positions.grades.map((g) => (
            <button
              key={g}
              type="button"
              className={`vertical-chip${grade === g ? " is-selected" : ""}`}
              onClick={() => {
                setGrade(grade === g ? "" : g);
                setPosition("");
              }}
            >
              {g}
            </button>
          ))}
        </div>

        <label style={{ marginTop: 10 }}>{t("recruiter.candidates.positionLabel")}</label>
        <select value={position} disabled={!vertical || !grade} onChange={(e) => setPosition(e.target.value)}>
          <option value="">{t("recruiter.candidates.positionPlaceholder")}</option>
          {positionOptions.map(([code, label]) => (
            <option key={code} value={label}>{label}</option>
          ))}
        </select>

        <label className="checkbox-row" style={{ marginTop: 10 }}>
          <input type="checkbox" checked={lookingOnly} onChange={(e) => setLookingOnly(e.target.checked)} />
          {t("recruiter.candidates.lookingOnlyLabel")}
        </label>
        <label className="checkbox-row">
          <input type="checkbox" checked={topRating} onChange={(e) => setTopRating(e.target.checked)} />
          {t("recruiter.candidates.topRatingLabel")}
        </label>

        <button type="button" className="btn" style={{ marginTop: 10 }} onClick={runFilterSearch}>
          {t("recruiter.candidates.submitBtn")}
        </button>
      </div>

      {state.loading && <Spinner>{t("search.submitting")}</Spinner>}
      {state.error === "notFound" && <Msg type="error">{t("recruiter.candidates.usernameNotFound")}</Msg>}
      {state.error && state.error !== "notFound" && <Msg type="error">{t("search.genericError")}</Msg>}

      {state.data?.mode === "profile" && (
        <div className="directory-results">
          <DirectoryRow r={state.data} onOpen={openCandidate} />
        </div>
      )}
      {state.data?.mode === "list" && (
        <>
          <div className="partner-meta">{t("recruiter.candidates.foundCount", { n: state.data.results.length })}</div>
          {state.data.results.length === 0 && <div className="partner-meta">{t("search.emptyList")}</div>}
          {state.data.results.length > 0 && (
            <div className="directory-results">
              {state.data.results.map((r) => (
                <DirectoryRow key={r.user_id} r={r} onOpen={openCandidate} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
