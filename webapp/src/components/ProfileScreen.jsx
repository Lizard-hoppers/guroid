import { useEffect, useState } from "react";
import { getMe, ApiError } from "../api.js";
import { Spinner, Msg } from "./Shared.jsx";
import { PrivacyToggles } from "./PrivacyToggles.jsx";
import { ProfileHub } from "./profile/ProfileHub.jsx";
import { RatingSubscreen } from "./profile/RatingSubscreen.jsx";
import { CvSubscreen } from "./profile/CvSubscreen.jsx";
import { ContactsSubscreen } from "./profile/ContactsSubscreen.jsx";
import { OffersSubscreen } from "./profile/OffersSubscreen.jsx";
import { QrSubscreen } from "./profile/QrSubscreen.jsx";
import { MessagesScreen } from "./profile/MessagesScreen.jsx";
import { OnboardingScreen } from "./profile/OnboardingScreen.jsx";
import { RecruiterHub } from "./profile/RecruiterHub.jsx";
import { RecruiterHistorySubscreen } from "./profile/RecruiterHistorySubscreen.jsx";
import { RecruiterCandidatesScreen } from "./profile/RecruiterCandidatesScreen.jsx";
import { RecruiterResponsesSubscreen } from "./profile/RecruiterResponsesSubscreen.jsx";
import { CompanyHub } from "./profile/CompanyHub.jsx";
import { ConfirmScreen } from "./ConfirmScreen.jsx";
import { useLang } from "../i18n.jsx";

// Переключатель Личный/Рекрутер/Компания (Фаза 3, 12.08.2026; Компания
// добавлена 16-17.08.2026) — рендерится только на "хабах" (ProfileHub /
// RecruiterHub / CompanyHub), не внутри под-экранов, чтобы не
// загромождать сфокусированные single-purpose экраны.
function WorkspaceSwitch({ workspace, onChange }) {
  const { t } = useLang();
  return (
    <div className="workspace-switch">
      <button
        type="button"
        className={workspace === "personal" ? "is-active" : ""}
        onClick={() => onChange("personal")}
      >
        {t("workspace.personal")}
      </button>
      <button
        type="button"
        className={workspace === "recruiter" ? "is-active" : ""}
        onClick={() => onChange("recruiter")}
      >
        {t("workspace.recruiter")}
      </button>
      <button
        type="button"
        className={workspace === "company" ? "is-active" : ""}
        onClick={() => onChange("company")}
      >
        {t("workspace.company")}
      </button>
    </div>
  );
}

export function ProfileScreen({
  onNavigate, messageTargetId, onConsumeMessageTarget,
  hireConfirmPrefill, onConsumeHireConfirmPrefill,
}) {
  const { t } = useLang();
  const [workspace, setWorkspace] = useState("personal");
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [recruiterState, setRecruiterState] = useState({ loading: true, data: null, error: null });
  const [companyState, setCompanyState] = useState({ loading: true, data: null, error: null });
  // null | "rating" | "cv" | "contacts" | "offers" | "messages" | "qr" |
  // "recruiter-confirm" | "recruiter-history" | "recruiter-candidates" |
  // "recruiter-responses" | "recruiter-qr" (26.08.2026, кабинет "Рекрутер")
  const [sub, setSub] = useState(null);
  // "Найти кандидата" -> "Написать" (26.08.2026) — ОТДЕЛЬНЫЙ таргет от
  // messageTargetId личного профиля, чтобы не путать deep-link/поиск с
  // рекрутерским компоузом (тот тегируется via_workspace="recruiter",
  // см. openRecruiterMessages).
  const [recruiterMessageTargetId, setRecruiterMessageTargetId] = useState(null);
  // Префилл формы "Подтвердить найм" — либо из PercentileBlock (null, как
  // раньше), либо из отклика на вакансию (username кандидата + вертикаль/
  // грейд/должность, см. goToHireConfirm/ConfirmScreen.jsx).
  const [confirmPrefill, setConfirmPrefill] = useState(null);

  function switchWorkspace(next) {
    setWorkspace(next);
    setSub(null); // подэкраны личного режима не имеют смысла в рекрутерском и наоборот
  }

  function goToHireConfirm(prefill) {
    setConfirmPrefill(prefill || null);
    setWorkspace("recruiter");
    setSub("recruiter-confirm");
  }

  // Межвкладочный переход "Подтвердить найм" из вкладки Вакансии (App.jsx,
  // hireConfirmPrefill) — так же, как messageTargetId ниже, форсит нужный
  // workspace/sub, когда приходит новое значение.
  useEffect(() => {
    if (hireConfirmPrefill != null) {
      goToHireConfirm(hireConfirmPrefill);
      onConsumeHireConfirmPrefill();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hireConfirmPrefill]);

  // Заход сразу в сообщения — кнопка "Написать" в поиске или deep-link из
  // уведомления бота ?thread=<id> (см. App.jsx), консьюмится MessagesScreen'ом.
  // Единый инбокс общий для всех кабинетов (ТЗ "Гуро рекрутер каб", 2.7) —
  // принудительно возвращаем workspace в "personal", иначе если юзер был на
  // вкладке "Рекрутер", сообщение открылось бы "внутри" recruiter-ветки
  // рендера, где sub="messages" ещё не обработан.
  useEffect(() => {
    if (messageTargetId != null) {
      setWorkspace("personal");
      setSub("messages");
    }
  }, [messageTargetId]);

  // Компоуз "Написать" из "Найти кандидата" (внутри кабинета Рекрутер) —
  // остаёмся в workspace="recruiter", чтобы сообщение тегировалось
  // via_workspace="recruiter" (см. MessagesScreen/ThreadScreen ниже).
  function openRecruiterMessages(userId) {
    setRecruiterMessageTargetId(String(userId));
    setSub("recruiter-messages");
  }

  function updateRecruiterActivityStatus(activity_status) {
    setRecruiterState((s) => ({ ...s, data: { ...s.data, activity_status } }));
  }

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((data) => !cancelled && setState({ loading: false, data, error: null }))
      .catch((error) => !cancelled && setState({ loading: false, data: null, error }));
    return () => {
      cancelled = true;
    };
  }, []);

  // Кабинет рекрутера грузится ЛЕНИВО — только когда юзер реально
  // переключился на вкладку "Рекрутер" (не на каждом заходе в Профиль).
  useEffect(() => {
    if (workspace !== "recruiter" || recruiterState.data) return;
    let cancelled = false;
    getMe({ workspace: "recruiter" })
      .then((data) => !cancelled && setRecruiterState({ loading: false, data, error: null }))
      .catch((error) => !cancelled && setRecruiterState({ loading: false, data: null, error }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace]);

  // Кабинет "Компания" — та же ленивая загрузка по факту переключения.
  useEffect(() => {
    if (workspace !== "company" || companyState.data) return;
    let cancelled = false;
    getMe({ workspace: "company" })
      .then((data) => !cancelled && setCompanyState({ loading: false, data, error: null }))
      .catch((error) => !cancelled && setCompanyState({ loading: false, data: null, error }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace]);

  if (state.loading) return <Spinner>{t("profileScreen.loading")}</Spinner>;

  if (state.error) {
    if (state.error instanceof ApiError && state.error.code === "NO_PROFILE") {
      return <OnboardingScreen />;
    }
    return <Msg type="error">{t("profileScreen.loadError")}</Msg>;
  }

  const p = state.data;

  function updatePrivacy(privacy) {
    setState((s) => ({ ...s, data: { ...s.data, privacy } }));
  }
  function updateField(field, value) {
    setState((s) => ({ ...s, data: { ...s.data, [field]: value } }));
  }
  function updateWorkStatus(work_status) {
    setState((s) => ({ ...s, data: { ...s.data, work_status } }));
  }
  function updateRecruiterPrivacy(privacy) {
    setRecruiterState((s) => ({ ...s, data: { ...s.data, privacy } }));
  }
  function updateRecruiterField(field, value) {
    setRecruiterState((s) => ({ ...s, data: { ...s.data, [field]: value } }));
  }
  function updateCompanyPrivacy(privacy) {
    setCompanyState((s) => ({ ...s, data: { ...s.data, privacy } }));
  }
  function updateCompanyField(field, value) {
    setCompanyState((s) => ({ ...s, data: { ...s.data, [field]: value } }));
  }

  if (workspace === "recruiter") {
    if (sub === "recruiter-confirm") {
      return (
        <ConfirmScreen
          forcedType="hire"
          prefill={confirmPrefill}
          onBack={() => {
            setSub(null);
            setConfirmPrefill(null);
          }}
        />
      );
    }
    if (sub === "recruiter-history") {
      return <RecruiterHistorySubscreen partners={p.partners} onBack={() => setSub(null)} />;
    }
    if (sub === "recruiter-candidates") {
      return <RecruiterCandidatesScreen onBack={() => setSub(null)} onWrite={openRecruiterMessages} />;
    }
    if (sub === "recruiter-responses") {
      return (
        <RecruiterResponsesSubscreen
          onBack={() => setSub(null)}
          onWrite={openRecruiterMessages}
          onConfirmHire={goToHireConfirm}
        />
      );
    }
    if (sub === "recruiter-qr") {
      return <QrSubscreen workspace="recruiter" onBack={() => setSub(null)} />;
    }
    if (sub === "recruiter-messages") {
      return (
        <MessagesScreen
          initialThreadUserId={recruiterMessageTargetId}
          onConsumeInitialThread={() => setRecruiterMessageTargetId(null)}
          onBack={() => setSub(null)}
          viaWorkspace="recruiter"
        />
      );
    }
    if (sub === "messages") {
      return <MessagesScreen onBack={() => setSub(null)} />;
    }
    return (
      <div>
        <WorkspaceSwitch workspace={workspace} onChange={switchWorkspace} />
        {recruiterState.loading && <Spinner>{t("recruiter.loading")}</Spinner>}
        {recruiterState.error && <Msg type="error">{t("recruiter.loadError")}</Msg>}
        {recruiterState.data && (
          <RecruiterHub
            data={recruiterState.data}
            onFieldSaved={updateRecruiterField}
            onPrivacyChange={updateRecruiterPrivacy}
            onActivityChange={updateRecruiterActivityStatus}
            onNavigateSub={setSub}
            onNavigateTab={onNavigate}
            onSubscribed={() =>
              setRecruiterState((s) => ({ ...s, data: { ...s.data, is_recruiter_subscribed: true } }))
            }
          />
        )}
      </div>
    );
  }

  if (workspace === "company") {
    return (
      <div>
        <WorkspaceSwitch workspace={workspace} onChange={switchWorkspace} />
        {companyState.loading && <Spinner>{t("company.loading")}</Spinner>}
        {companyState.error && <Msg type="error">{t("company.loadError")}</Msg>}
        {companyState.data && (
          <CompanyHub
            data={companyState.data}
            onFieldSaved={updateCompanyField}
            onPrivacyChange={updateCompanyPrivacy}
            onSubscribed={() =>
              setCompanyState((s) => ({ ...s, data: { ...s.data, is_company_subscribed: true } }))
            }
          />
        )}
      </div>
    );
  }

  if (sub === "rating") {
    return (
      <RatingSubscreen
        profile={p}
        privacy={p.privacy}
        onPrivacyChange={updatePrivacy}
        onBack={() => setSub(null)}
        onNavigate={onNavigate}
      />
    );
  }
  if (sub === "cv") {
    return (
      <CvSubscreen
        profile={p}
        privacy={p.privacy}
        onPrivacyChange={updatePrivacy}
        onFieldSaved={updateField}
        onBack={() => setSub(null)}
      />
    );
  }
  if (sub === "contacts") {
    return (
      <ContactsSubscreen
        profile={p}
        privacy={p.privacy}
        onPrivacyChange={updatePrivacy}
        onFieldSaved={updateField}
        onBack={() => setSub(null)}
        onNavigateSub={setSub}
      />
    );
  }
  if (sub === "offers") {
    return (
      <OffersSubscreen
        profile={p}
        privacy={p.privacy}
        onPrivacyChange={updatePrivacy}
        onFieldSaved={updateField}
        onBack={() => setSub(null)}
      />
    );
  }
  if (sub === "qr") {
    return <QrSubscreen onBack={() => setSub(null)} />;
  }
  if (sub === "messages") {
    return (
      <MessagesScreen
        initialThreadUserId={messageTargetId}
        onConsumeInitialThread={onConsumeMessageTarget}
        onBack={() => setSub(null)}
      />
    );
  }

  return (
    <div>
      <WorkspaceSwitch workspace={workspace} onChange={switchWorkspace} />
      <ProfileHub
        profile={p}
        privacy={p.privacy}
        onPrivacyChange={updatePrivacy}
        onNavigateSub={setSub}
        onWorkStatusChange={updateWorkStatus}
      />
    </div>
  );
}
