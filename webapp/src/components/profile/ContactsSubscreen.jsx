import { useState } from "react";
import { getInviteLink } from "../../api.js";
import { EditableField, Msg } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";
import { openTelegramLink, haptic } from "../../telegram.js";
import { useLang } from "../../i18n.jsx";

// «Пригласить коллегу» (Фаза 2, 11.08.2026, по PDF-фидбеку владельца) —
// персональная одноразовая реф-ссылка (см. /api/invite_link ->
// handlers/referral.py-совместимый формат), шарится через универсальный
// t.me/share — работает даже там, где нет нативного Telegram.WebApp.shareURL.
function InviteColleagueButton() {
  const { t } = useLang();
  const [state, setState] = useState({ loading: false, error: false });

  async function onClick() {
    setState({ loading: true, error: false });
    try {
      const { link } = await getInviteLink();
      haptic("light");
      const text = t("contacts.inviteShareText");
      openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`);
      setState({ loading: false, error: false });
    } catch {
      setState({ loading: false, error: true });
      haptic("error");
    }
  }

  return (
    <div style={{ marginTop: 14 }}>
      <button type="button" className="btn secondary" onClick={onClick} disabled={state.loading}>
        {state.loading ? t("contacts.inviteBusy") : t("contacts.inviteBtn")}
      </button>
      <Msg type="error">{state.error ? t("contacts.inviteError") : null}</Msg>
    </div>
  );
}

export function ContactsSubscreen({ profile, privacy, onPrivacyChange, onFieldSaved, onBack, onNavigateSub }) {
  const { t } = useLang();
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        {t("common.back")}
      </button>
      <div className="card">
        <h3>{t("contacts.title")}</h3>
        <div className="partner-meta">{t("contacts.telegram")}: @{profile.username}</div>
        {profile.linkedin ? (
          <div className="partner-meta" style={{ marginTop: 8 }}>
            LinkedIn: {profile.linkedin}
          </div>
        ) : (
          <div className="editable-field-empty" style={{ marginTop: 8 }}>
            {t("contacts.linkedinEmpty")}
          </div>
        )}
        <EditableField
          field="website"
          label={t("contacts.websiteLabel")}
          placeholder="example.com"
          value={profile.website}
          onSaved={(v) => onFieldSaved("website", v)}
        />
        <button
          type="button"
          className="profile-menu-item"
          style={{ marginTop: 10 }}
          onClick={() => onNavigateSub?.("qr")}
        >
          <span>{t("contacts.showQr")}</span>
          <span className="profile-menu-item-chevron">›</span>
        </button>
        <InviteColleagueButton />
      </div>
      <PrivacyToggles
        privacy={privacy}
        onChange={onPrivacyChange}
        fields={["show_contacts"]}
        hint={t("contacts.privacyHint")}
      />
    </div>
  );
}
