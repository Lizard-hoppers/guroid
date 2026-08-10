import { useEffect, useState } from "react";
import { getMe, ApiError } from "../api.js";
import { Spinner, Msg, MetricsRow, PartnersList } from "./Shared.jsx";
import { PrivacyToggles } from "./PrivacyToggles.jsx";
import { DeveloperShowcase } from "./DeveloperShowcase.jsx";

export function ProfileScreen() {
  const [state, setState] = useState({ loading: true, data: null, error: null });

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
      return (
        <div className="card">
          <h3>Профиль не найден</h3>
          <div className="partner-meta">
            Чтобы получить GURO ID, сначала пройдите анкету в @GamblingCommunitybot.
          </div>
        </div>
      );
    }
    return <Msg type="error">Не удалось загрузить профиль. Попробуйте позже.</Msg>;
  }

  const p = state.data;

  const privacyBlock = (
    <PrivacyToggles
      privacy={p.privacy}
      onChange={(privacy) => setState((s) => ({ ...s, data: { ...s.data, privacy } }))}
    />
  );

  // Приватность — настройка САМОГО аккаунта, не данные из анкеты, поэтому
  // рендерится ВСЕГДА, даже когда вместо обычного профиля показана витрина
  // разработчика (иначе автор не смог бы увидеть свои же тумблеры).
  if (p.is_showcase) {
    return (
      <div>
        <DeveloperShowcase data={p} />
        {privacyBlock}
      </div>
    );
  }

  return (
    <div>
      <div className="card">
        <h2>{p.name || (p.username ? `@${p.username}` : "Без имени")}</h2>
        {p.vertical && <div className="partner-meta">Вертикаль: {p.vertical}</div>}
        {p.company && <div className="partner-meta">Компания: {p.company}</div>}
        <MetricsRow
          reputation={p.reputation_score}
          partnerships={p.confirmed_partnerships}
          daysInCommunity={p.days_in_community}
        />
      </div>
      <div className="card">
        <h3>Партнёрства</h3>
        <PartnersList
          partners={p.partners}
          emptyHint="Пока нет подтверждённых партнёрств. Отметьте сотрудничество во вкладке «Подтвердить»."
        />
      </div>
      {privacyBlock}
    </div>
  );
}
