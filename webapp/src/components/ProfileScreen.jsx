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
import { useLang } from "../i18n.jsx";

// Переключатель Личный/Рекрутер (Фаза 3, 12.08.2026) — рендерится только
// на "хабах" (ProfileHub / RecruiterHub), не внутри под-экранов, чтобы не
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
    </div>
  );
}

export function ProfileScreen({ onNavigate, messageTargetId, onConsumeMessageTarget }) {
  const { t } = useLang();
  const [workspace, setWorkspace] = useState("personal");
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [recruiterState, setRecruiterState] = useState({ loading: true, data: null, error: null });
  const [sub, setSub] = useState(null); // null | "rating" | "cv" | "contacts" | "offers" | "messages" | "qr"

  function switchWorkspace(next) {
    setWorkspace(next);
    setSub(null); // подэкраны личного режима не имеют смысла в рекрутерском и наоборот
  }

  // Заход сразу в сообщения — кнопка "Написать" в поиске или deep-link из
  // уведомления бота ?thread=<id> (см. App.jsx), консьюмится MessagesScreen'ом.
  useEffect(() => {
    if (messageTargetId != null) setSub("messages");
  }, [messageTargetId]);

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

  if (workspace === "recruiter") {
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
            onSubscribed={() =>
              setRecruiterState((s) => ({ ...s, data: { ...s.data, is_recruiter_subscribed: true } }))
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
