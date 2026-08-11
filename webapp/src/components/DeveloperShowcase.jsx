import { openTelegramLink } from "../telegram.js";
import { useLang } from "../i18n.jsx";

// Форма данных строго повторяет guro_showcase.PAYLOAD на бэкенде — витрина
// статична (не из profiles/guro_users), см. guro_showcase.py. Сам контент
// витрины (tagline/bio/projects) — самореклама автора на русском, backend
// не отдаёт EN-версию, переводить не просили (не часть фичи двуязычия
// приложения, 12.08.2026) — переведена только окружающая UI-обвязка.
export function DeveloperShowcase({ data }) {
  const { t } = useLang();
  const s = data.showcase;
  return (
    <div className="card">
      <span className="showcase-badge">{t("showcase.role")}</span>
      <h2 style={{ marginTop: 10 }}>{data.name}</h2>
      <div className="showcase-tagline">{s.tagline}</div>
      <div className="showcase-bio">{s.bio}</div>
      <div className="showcase-stack">
        {s.tech_stack.map((tech) => (
          <span className="chip" key={tech}>
            {tech}
          </span>
        ))}
      </div>
      <h3 style={{ marginTop: 18 }}>{t("showcase.portfolio")}</h3>
      {s.projects.map((proj) => (
        <div className="project-card" key={proj.name}>
          <div className="project-head">
            <span className="project-name">{proj.name}</span>
            <span className="project-tag">{proj.tag}</span>
          </div>
          <div className="project-desc">{proj.description}</div>
        </div>
      ))}
      <button className="btn" onClick={() => openTelegramLink(s.contact_url)}>
        {t("showcase.contact")}
      </button>
    </div>
  );
}
