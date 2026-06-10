import "./Team.css";

const TEAM = [
  {
    name: "Michael Paonam",
    role: "Architecture & Platform",
    bio: "Agentic systems, runtime security primitives, observability design.",
    github: "https://github.com/MichaelPaonam",
  },
  {
    name: "Ashiha Maheshkumar",
    role: "Threat Engineering",
    bio: "Adversarial scenarios, data pipeline security, cloud deployment.",
    github: "https://github.com/ashihams",
  },
  {
    name: "Moris Takhellambam",
    role: "Agent Engineering",
    bio: "Agent runtime, tool integrations, ADK platform work.",
    github: "https://github.com/MorisTakhellambam",
  },
];

export function Team() {
  return (
    <section class="section" id="team">
      <div class="container">
        <p class="section__label">Built By</p>
        <h2 class="section__title">The Team</h2>
        <p class="section__lead">
          Builders of the immune system for agentic AI. We work where
          agents meet the real world — tools, data, untrusted inputs —
          and make that boundary defensible.
        </p>

        <div class="team__grid">
          {TEAM.map((member) => (
            <article key={member.name} class="card cyber-chamfer team__member">
              <h3 class="team__name">
                {member.github ? (
                  <a href={member.github} target="_blank" rel="noreferrer noopener">
                    {member.name}
                  </a>
                ) : (
                  member.name
                )}
              </h3>
              <p class="team__role">{member.role}</p>
              <p class="team__bio">{member.bio}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer class="footer">
      <div class="container footer__inner">
        <p class="footer__copy">
          © 2026 SentinelDS · Emit → Detect → Decide → Enforce
          <br />
          <small>
            Originally built at the Google Cloud Rapid Agent Hackathon, 2026.
          </small>
        </p>
        <ul class="footer__links">
          <li>
            <a
              href="https://github.com/MichaelPaonam/sentinelds"
              target="_blank"
              rel="noreferrer noopener"
            >
              GitHub
            </a>
          </li>
          <li>
            <a href="#top">Back to top</a>
          </li>
        </ul>
      </div>
    </footer>
  );
}
