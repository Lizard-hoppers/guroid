import { openTelegramLink } from "../telegram.js";

// Форма данных строго повторяет guro_showcase.PAYLOAD на бэкенде — витрина
// статична (не из profiles/guro_users), см. guro_showcase.py.
export function DeveloperShowcase({ data }) {
  const s = data.showcase;
  return (
    <div className="card">
      <span className="showcase-badge">💻 Разработчик ботов и Mini Apps</span>
      <h2 style={{ marginTop: 10 }}>{data.name}</h2>
      <div className="showcase-tagline">{s.tagline}</div>
      <div className="showcase-bio">{s.bio}</div>
      <div className="showcase-stack">
        {s.tech_stack.map((t) => (
          <span className="chip" key={t}>
            {t}
          </span>
        ))}
      </div>
      <h3 style={{ marginTop: 18 }}>Портфолио</h3>
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
        ✉️ Написать в Telegram
      </button>
    </div>
  );
}
