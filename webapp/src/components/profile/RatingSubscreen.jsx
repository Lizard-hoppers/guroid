import { MetricsRow, PartnersList } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";

export function RatingSubscreen({ profile, privacy, onPrivacyChange, onBack, onNavigate }) {
  return (
    <div>
      <button type="button" className="subscreen-back" onClick={onBack}>
        ‹ Профиль
      </button>

      {!profile.is_subscribed && (
        <div className="card subscription-gate-note">
          <strong>Рейтинг и сделки скрыты</strong>
          <p className="partner-meta">
            Без активной подписки рейтинг и история сделок не видны — ни вам, ни другим. Ничего
            не удалено: как только подписка возобновится, всё вернётся как было.
          </p>
          <button className="btn" style={{ width: "auto", padding: "10px 20px" }} onClick={() => onNavigate?.("subscribe")}>
            Оформить подписку
          </button>
        </div>
      )}

      <div className="card">
        <h3>Мой рейтинг</h3>
        <MetricsRow
          reputation={profile.reputation_score}
          partnerships={profile.confirmed_partnerships}
          daysInCommunity={profile.days_in_community}
        />
      </div>
      <div className="card">
        <h3>Партнёрства</h3>
        <PartnersList
          partners={profile.partners}
          emptyHint="Пока нет подтверждённых партнёрств. Отметьте сотрудничество во вкладке «Подтвердить»."
        />
      </div>
      <PrivacyToggles
        privacy={privacy}
        onChange={onPrivacyChange}
        fields={["show_reputation", "show_tenure"]}
        hint="Управляет тем, что видят чужие при поиске вас. Партнёрства видны всем ЧУЖИМ всегда (это ядро смысла GURO ID) — при условии, что у вас активна подписка (см. выше)."
      />
    </div>
  );
}
