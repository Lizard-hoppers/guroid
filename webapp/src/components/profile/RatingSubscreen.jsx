import { useState } from "react";
import { MetricsRow, PartnersList } from "../Shared.jsx";
import { PrivacyToggles } from "../PrivacyToggles.jsx";

// Подсказка "как поднять рейтинг" (11.08.2026, по фидбеку владельца —
// PDF-разбор шаг "У вас низкий рейтинг в индустрии. Как исправить?" не вёл
// никуда, копия ниже — то же объяснение, что он сам продиктовал). Тот же
// expand-паттерн, что "Подробнее" в OnboardingScreen.jsx (onboarding-more-link/
// onboarding-detail), для визуальной согласованности.
function RatingHelp() {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="card">
      <button type="button" className="onboarding-more-link" onClick={() => setExpanded((v) => !v)}>
        {expanded ? "Скрыть" : "Как поднять рейтинг?"}
      </button>
      {expanded && (
        <div className="onboarding-detail">
          <p>
            Рейтинг — это сколько людей подтвердило успешные сделки с вами. У кого высокий
            рейтинг — с тем человеком меньше рисков попасть на деньги.
          </p>
          <p>Рейтинг формируется от сделок и найма.</p>
          <p>
            Вы и ваш партнёр, с которым уже была успешная сделка, добавляете друг друга по кнопке
            «Подтвердить партнёрство» во вкладке «Подтвердить». Чем больше успешных сделок или
            наймов подтверждено — тем выше рейтинг и тем охотнее люди из индустрии пойдут с вами
            на контакт. Можно добавить всех, с кем вы работали ещё до появления GURO ID.
          </p>
        </div>
      )}
    </div>
  );
}

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
      <RatingHelp />
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
