import { useEffect, useState } from "react";
import { getMe, ApiError } from "../api.js";
import { Spinner, Msg } from "./Shared.jsx";
import { PrivacyToggles, PRIVACY_LABELS } from "./PrivacyToggles.jsx";
import { DeveloperShowcase } from "./DeveloperShowcase.jsx";
import { ProfileHub } from "./profile/ProfileHub.jsx";
import { RatingSubscreen } from "./profile/RatingSubscreen.jsx";
import { CvSubscreen } from "./profile/CvSubscreen.jsx";
import { ContactsSubscreen } from "./profile/ContactsSubscreen.jsx";
import { OffersSubscreen } from "./profile/OffersSubscreen.jsx";
import { QrSubscreen } from "./profile/QrSubscreen.jsx";
import { OnboardingScreen } from "./profile/OnboardingScreen.jsx";

export function ProfileScreen({ onNavigate }) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [sub, setSub] = useState(null); // null | "rating" | "cv" | "contacts" | "offers"

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((data) => !cancelled && setState({ loading: false, data, error: null }))
      .catch((error) => !cancelled && setState({ loading: false, data: null, error }));
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.loading) return <Spinner>Загружаем профиль…</Spinner>;

  if (state.error) {
    if (state.error instanceof ApiError && state.error.code === "NO_PROFILE") {
      return <OnboardingScreen />;
    }
    return <Msg type="error">Не удалось загрузить профиль. Попробуйте позже.</Msg>;
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

  // Приватность — настройка САМОГО аккаунта, не данные из анкеты, поэтому
  // рендерится ВСЕГДА, даже когда вместо обычного профиля показана витрина
  // разработчика (иначе автор не смог бы увидеть свои же тумблеры).
  if (p.is_showcase) {
    return (
      <div>
        <DeveloperShowcase data={p} />
        <PrivacyToggles
          privacy={p.privacy}
          onChange={updatePrivacy}
          fields={Object.keys(PRIVACY_LABELS)}
          hint="По умолчанию ничего не видно чужим, кроме факта участия в GURO ID и партнёрств."
        />
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

  return (
    <ProfileHub
      profile={p}
      privacy={p.privacy}
      onPrivacyChange={updatePrivacy}
      onNavigateSub={setSub}
      onWorkStatusChange={updateWorkStatus}
    />
  );
}
