import { useState } from "react";
import { openTelegramLink } from "../../telegram.js";

const VERTICALS = ["Гемблинг", "Бейтинг", "Крипто", "Нутра", "Дейтинг", "Е-коммерс", "Другое"];

// Экран первого запуска (нет анкеты -> нет профиля GURO ID) — по ручному
// эскизу заказчика: макет ID-карты с плейсхолдерами, короткое объяснение,
// раскрывающееся "Подробнее" с полным питчем + ценами, CTA на анкету бота.
export function OnboardingScreen() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div>
      <div className="card">
        <div className="profile-header-card onboarding-mock-card">
          <div className="profile-avatar-fallback onboarding-mock-avatar">🏃</div>
          <div className="profile-header-info">
            <h2 className="onboarding-mock-placeholder">Name?</h2>
            <div className="profile-header-sub onboarding-mock-placeholder">Position?</div>
            <div className="profile-header-sub onboarding-mock-placeholder">Company?</div>
          </div>
        </div>

        <h3 style={{ marginTop: 16 }}>Это ваша ID-карта</h3>
        <p className="partner-meta">
          Для загрузки CV, поиска работы, кандидатов и партнёров. А также есть рейтинг
          подтверждённых сделок и найма.{" "}
          <button type="button" className="onboarding-more-link" onClick={() => setExpanded((v) => !v)}>
            Подробнее
          </button>
        </p>

        {expanded && (
          <div className="onboarding-detail">
            <p>Вы платите за то, чтобы быть всегда сразу в 7 вертикалях:</p>
            <ul className="onboarding-verticals">
              {VERTICALS.map((v) => (
                <li key={v}>{v}</li>
              ))}
            </ul>
            <p>
              У вас появится специальная ID-карта. Каждый раз, когда у вас будет успешная сделка
              или найм, ваш партнёр подтверждает это — и на основании этого у вас будет рейтинг.
              Вам достаточно отправить свой юзернейм любому участнику индустрии: он, перейдя в
              ваш профиль, увидит, что с вами сотрудничали разные люди, были успешные сделки,
              найм.
            </p>
            <p>Также вы сможете загрузить своё резюме и найти работу. Функционал будет увеличиваться.</p>
            <p>
              При отсутствии активной подписки ваш рейтинг в индустрии скрывается — сотни сделок
              и успешных наймов пропадают из виду (сами данные не удаляются: как только подписка
              возобновится, всё вернётся как было).
            </p>
            <p>
              Подписка: <strong>$10/месяц</strong> или <strong>$99/год</strong> (в звёздах —
              650⭐ / 6600⭐).
            </p>
          </div>
        )}
      </div>

      <div className="card">
        <p className="partner-meta">
          Чтобы начать строить репутацию и карьеру — заполните анкету. В конце у вас будет выбор,
          какая информация будет общедоступна, а какая нет.
        </p>
        <button className="btn" onClick={() => openTelegramLink("https://t.me/GamblingCommunitybot")}>
          Заполнить анкету в боте
        </button>
      </div>
    </div>
  );
}
