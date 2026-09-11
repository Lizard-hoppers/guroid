import { useState } from "react";
import { registerProfile } from "../../api.js";
import { useLang, ONBOARDING_VERTICALS } from "../../i18n.jsx";
import { haptic, getSuggestedName } from "../../telegram.js";
import { usePositions } from "../VacanciesScreen.jsx";
import { SubscribeScreen } from "../SubscribeScreen.jsx";
import { Msg, Spinner } from "../Shared.jsx";

// Регистрация ПРЯМО в приложении (11.09.2026, дизайн-предложение
// «First-time flow: от первого экрана до оплаты»). Раньше единственный
// способ завести профиль GURO ID был через анкету в боте — этот экран
// заменяет статичный OnboardingScreen (кнопка «в бот») настоящей формой:
// ценность → анкета → живая карточка → подписка → готовый профиль.
//
// ПОЧЕМУ 3 ШАГА АНКЕТЫ, А НЕ 5, КАК В МАКЕТЕ ДИЗАЙНЕРА. В макете экран
// «Кем вы работаете» показывает вертикаль (чипы) и должность (список) на
// ОДНОМ экране, без отдельного шага «грейд» — и это работает: в
// professions_data.py каждый КОД должности существует только у ОДНОГО
// грейда в пределах вертикали (проверено, 0 пересечений), то есть грейд
// однозначно ВЫВОДИТСЯ из выбранной должности, отдельный вопрос про него
// не нужен. Реальных экранов с вводом — три: вертикаль+должность, имя,
// проверка перед публикацией. Растягивать до пяти ради совпадения с
// скриншотом означало бы либо дублировать вопрос о грейде (лишний шаг
// там, где дизайнер сам его убрал), либо вставлять пустые "шаги-затычки" —
// и то и другое хуже, чем честный «Шаг N из 3» при том же самом сборе
// данных. Ветку «Инвестор» (свой набор полей) сюда не пускаем — только в
// боте, это осознанное упрощение первой версии.
const VERTICALS = ["Gambling", "Betting", "Crypto", "Dating", "E-Commerce", "FinTech", "Nutra", "Other"];

const STEP_VALUE = "value";
const STEP_POSITION = "position";
const STEP_NAME = "name";
const STEP_REVIEW = "review";
const STEP_SUBSCRIBE = "subscribe";

const ANKETA_STEPS = [STEP_POSITION, STEP_NAME, STEP_REVIEW];

function AnketaProgress({ step, onBack }) {
  const { t } = useLang();
  const index = ANKETA_STEPS.indexOf(step);
  return (
    <div className="anketa-progress-wrap">
      <div className="anketa-progress-top">
        <button type="button" className="anketa-back" onClick={onBack}>
          {t("common.back")}
        </button>
        <span className="anketa-progress-label">
          {t("createProfile.stepLabel", { step: index + 1, total: ANKETA_STEPS.length })}
        </span>
      </div>
      <div className="anketa-progress-track">
        {ANKETA_STEPS.map((s, i) => (
          <div key={s} className={`anketa-progress-seg${i <= index ? " is-done" : ""}`} />
        ))}
      </div>
    </div>
  );
}

// Карточка "собирается на глазах" (макет, шаг 3 «Живое превью») — тот же
// внешний вид, что у настоящего профиля (.profile-header-card), просто с
// плейсхолдерами вместо ещё не введённых полей.
function LiveCard({ draft }) {
  const { t } = useLang();
  const initial = (draft.name || "?").trim().charAt(0).toUpperCase();
  return (
    <div className="card">
      <div className="profile-header-card">
        <div className="profile-avatar-fallback">{initial}</div>
        <div className="profile-header-info">
          <h2 className={draft.name ? "" : "onboarding-mock-placeholder"}>
            {draft.name || t("createProfile.namePlaceholderCard")}
          </h2>
          <div className={`profile-header-sub${draft.professionLabel ? "" : " onboarding-mock-placeholder"}`}>
            {draft.professionLabel
              ? `${draft.professionLabel} · ${draft.vertical}`
              : t("createProfile.positionPlaceholderCard")}
          </div>
        </div>
      </div>
    </div>
  );
}

function ValueStep({ onStart }) {
  const { t, lang } = useLang();
  const [expanded, setExpanded] = useState(false);
  const verticals = ONBOARDING_VERTICALS[lang] || ONBOARDING_VERTICALS.ru;
  return (
    <div>
      <div className="card">
        <div className="profile-header-card onboarding-mock-card">
          <div className="profile-avatar-fallback onboarding-mock-avatar">?</div>
          <div className="profile-header-info">
            <h2 className="onboarding-mock-placeholder">{t("createProfile.emptyName")}</h2>
            <div className="profile-header-sub onboarding-mock-placeholder">{t("createProfile.emptyPosition")}</div>
          </div>
        </div>

        {/* Пример "прокачанного" профиля — реальный масштаб рейтинга
            (медиана среди подписанных ~4-5, сильный профиль — около 8), а
            не выдуманное число: проверено на боевой базе 11.09.2026, чтобы
            новый человек не сравнивал свой первый день с фантазией. */}
        <div className="profile-header-card" style={{ marginTop: 16 }}>
          <div className="profile-avatar-fallback">А</div>
          <div className="profile-header-info">
            <h2>{t("createProfile.exampleName")}</h2>
            <div className="profile-header-sub">{t("createProfile.examplePosition")}</div>
          </div>
        </div>

        <h3 style={{ marginTop: 16 }}>{t("onboarding.title")}</h3>
        <p className="partner-meta">
          {t("onboarding.intro")}{" "}
          <button type="button" className="onboarding-more-link" onClick={() => setExpanded((v) => !v)}>
            <span className="link-underline">{t("onboarding.more")}</span>
          </button>
        </p>

        {expanded && (
          <div className="onboarding-detail">
            <p>{t("onboarding.detail1")}</p>
            <ul className="onboarding-verticals">
              {verticals.map((v) => (
                <li key={v}>{v}</li>
              ))}
            </ul>
            <p>{t("onboarding.detail2")}</p>
            <p>{t("onboarding.detail3")}</p>
          </div>
        )}
      </div>

      <div className="card">
        <p className="partner-meta">{t("createProfile.ctaHint")}</p>
        <button className="btn" onClick={onStart}>
          {t("createProfile.ctaBtn")}
        </button>
      </div>
    </div>
  );
}

function PositionStep({ draft, onChange, onNext }) {
  const { t } = useLang();
  const positions = usePositions();
  const flatOptions = draft.vertical ? flattenByGrade(positions.professions[draft.vertical]) : [];
  const canNext = !!draft.vertical && !!draft.profession;

  return (
    <div className="card">
      <h3>{t("createProfile.positionTitle")}</h3>

      <label>{t("vacancies.form.verticalLabel")}</label>
      <div className="vertical-chips">
        {VERTICALS.map((v) => (
          <button
            key={v}
            type="button"
            className={`vertical-chip${draft.vertical === v ? " is-selected" : ""}`}
            onClick={() => {
              haptic("select");
              onChange({ vertical: v, grade: "", profession: "", professionLabel: "" });
            }}
          >
            {v}
          </button>
        ))}
      </div>

      <label style={{ marginTop: 12 }}>{t("vacancies.form.positionLabel")}</label>
      <select
        value={draft.profession}
        disabled={!draft.vertical || positions.loading}
        onChange={(e) => {
          const opt = flatOptions.find((o) => o.label === e.target.value);
          if (!opt) return;
          onChange({ profession: opt.label, professionLabel: opt.label, grade: opt.grade });
        }}
      >
        <option value="">{t("vacancies.form.positionPlaceholder")}</option>
        {positions.grades.map((g) => {
          const group = flatOptions.filter((o) => o.grade === g);
          if (!group.length) return null;
          return (
            <optgroup key={g} label={g}>
              {group.map((o) => (
                <option key={o.code} value={o.label}>{o.label}</option>
              ))}
            </optgroup>
          );
        })}
      </select>

      <button className="btn" style={{ marginTop: 16 }} disabled={!canNext} onClick={onNext}>
        {t("createProfile.nextBtn", { left: 2 })}
      </button>
    </div>
  );
}

function flattenByGrade(professionsForVertical) {
  if (!professionsForVertical) return [];
  const out = [];
  for (const grade of Object.keys(professionsForVertical)) {
    for (const [code, label] of professionsForVertical[grade]) {
      out.push({ code, label, grade });
    }
  }
  return out;
}

function NameStep({ draft, onChange, onNext }) {
  const { t } = useLang();
  return (
    <div className="card">
      <h3>{t("createProfile.nameTitle")}</h3>
      <label>{t("createProfile.nameLabel")}</label>
      <input
        type="text"
        value={draft.name}
        maxLength={100}
        placeholder={t("createProfile.namePlaceholder")}
        onChange={(e) => onChange({ name: e.target.value })}
      />
      <button className="btn" style={{ marginTop: 16 }} disabled={!draft.name.trim()} onClick={onNext}>
        {t("createProfile.nextBtn", { left: 1 })}
      </button>
    </div>
  );
}

function ReviewStep({ draft, onSubmit, saving }) {
  const { t } = useLang();
  return (
    <div className="card">
      <h3>{t("createProfile.reviewTitle")}</h3>
      <p className="partner-meta">{t("createProfile.reviewIntro")}</p>

      <div className="compare-row"><span>{t("editProfile.name")}</span><span>{draft.name}</span></div>
      <div className="compare-row"><span>{t("editProfile.vertical")}</span><span>{draft.vertical}</span></div>
      <div className="compare-row"><span>{t("editProfile.profession")}</span><span>{draft.professionLabel}</span></div>

      <button className="btn" style={{ marginTop: 16 }} disabled={saving} onClick={onSubmit}>
        {saving ? t("createProfile.publishing") : t("createProfile.publishBtn")}
      </button>
      <p className="partner-meta" style={{ marginTop: 8 }}>{t("createProfile.reviewNextHint")}</p>
    </div>
  );
}

export function CreateProfileFlow({ onDone }) {
  const { t, lang } = useLang();
  const [step, setStep] = useState(STEP_VALUE);
  const [draft, setDraft] = useState({
    vertical: "", grade: "", profession: "", professionLabel: "",
    name: getSuggestedName(),
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function patch(next) {
    setDraft((d) => ({ ...d, ...next }));
  }

  function goBack() {
    haptic("light");
    const i = ANKETA_STEPS.indexOf(step);
    if (i <= 0) {
      setStep(STEP_VALUE);
    } else {
      setStep(ANKETA_STEPS[i - 1]);
    }
  }

  async function submit() {
    setSaving(true);
    setError("");
    try {
      await registerProfile({
        name: draft.name.trim(), vertical: draft.vertical,
        grade: draft.grade, profession: draft.profession, lang,
      });
      haptic("success");
      setStep(STEP_SUBSCRIBE);
    } catch {
      setError(t("createProfile.saveError"));
      haptic("error");
    } finally {
      setSaving(false);
    }
  }

  if (step === STEP_VALUE) {
    return <ValueStep onStart={() => setStep(STEP_POSITION)} />;
  }

  if (step === STEP_SUBSCRIBE) {
    // Экран "Ваш профиль готов к публикации" (макет, шаг 4) — профиль уже
    // сохранён, дальше обычный экран подписки (крипта первой, скидка
    // первого дня — оба уже встроены в сам SubscribeScreen). "Пропустить"
    // ведёт в приложение сразу: анкета не пропадает, вернуться к оплате
    // можно в любой момент через обычную вкладку "Подписка".
    return (
      <div>
        <div className="card">
          <div className="section-eyebrow">{t("createProfile.readyEyebrow")}</div>
          <h3>{t("createProfile.readyTitle")}</h3>
          <p className="partner-meta">{t("createProfile.readyIntro")}</p>
        </div>
        <SubscribeScreen product="guro_id" onSubscribed={onDone} />
        <div className="card">
          <button type="button" className="onboarding-more-link" onClick={onDone}>
            <span className="link-underline">{t("createProfile.skipForNow")}</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <AnketaProgress step={step} onBack={goBack} />
      <LiveCard draft={draft} />
      {step === STEP_POSITION && <PositionStep draft={draft} onChange={patch} onNext={() => setStep(STEP_NAME)} />}
      {step === STEP_NAME && <NameStep draft={draft} onChange={patch} onNext={() => setStep(STEP_REVIEW)} />}
      {step === STEP_REVIEW && <ReviewStep draft={draft} onSubmit={submit} saving={saving} />}
      <Msg type="error">{error}</Msg>
    </div>
  );
}
