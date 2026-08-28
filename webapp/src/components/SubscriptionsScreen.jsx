import { useEffect, useState } from "react";
import { getMe } from "../api.js";
import { SubscribeScreen } from "./SubscribeScreen.jsx";
import { useLang } from "../i18n.jsx";
import { formatDate } from "../utils.js";

// Строка одной "другой" подписки (28.08.2026, фидбек владельца: таб
// "Подписка" показывал только личную GURO ID, хотя у Рекрутера и Компании
// тоже есть свои отдельные подписки — по логике все три должны быть видны
// в одном месте). Полную форму оплаты сюда не дублируем (уже есть внутри
// каждого кабинета) — тут только статус + переход в нужный воркспейс,
// используя workspace/onWorkspaceChange, поднятые в App.jsx для таба
// "Сделки" (та же межтабовая память, что и там).
function OtherSubscriptionRow({ label, active, expiresAt, tierLabel, onOpen }) {
  const { t } = useLang();
  return (
    <button type="button" className="profile-menu-item" onClick={onOpen}>
      <span>
        <div>{label}{tierLabel ? ` · ${tierLabel}` : ""}</div>
        <div className="partner-meta">
          {active
            ? t("subscriptions.activeUntil", { date: formatDate(expiresAt) })
            : t("subscriptions.notSubscribed")}
        </div>
      </span>
      <span className="profile-menu-item-chevron">›</span>
    </button>
  );
}

export function SubscriptionsScreen(props) {
  const { t } = useLang();
  const [recruiter, setRecruiter] = useState(null);
  const [company, setCompany] = useState(null);

  useEffect(() => {
    getMe({ workspace: "recruiter" }).then(setRecruiter).catch(() => {});
    getMe({ workspace: "company" }).then(setCompany).catch(() => {});
  }, []);

  function openWorkspace(workspace) {
    props.onWorkspaceChange?.(workspace);
    props.onNavigate?.("profile");
  }

  return (
    <div>
      <SubscribeScreen product="guro_id" />

      <div className="card">
        <h3>{t("subscriptions.otherTitle")}</h3>
        <OtherSubscriptionRow
          label={t("workspace.recruiter")}
          active={!!recruiter?.is_recruiter_subscribed}
          expiresAt={recruiter?.recruiter_subscription_expires_at}
          onOpen={() => openWorkspace("recruiter")}
        />
        <OtherSubscriptionRow
          label={t("workspace.company")}
          active={!!company?.is_company_subscribed}
          expiresAt={company?.company_subscription_expires_at}
          tierLabel={company?.is_company_subscribed ? t(`company.tier.${company.company_tier || "basic"}`) : null}
          onOpen={() => openWorkspace("company")}
        />
      </div>
    </div>
  );
}
