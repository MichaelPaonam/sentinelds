import "./Team.css";

const TEAM = [
  {
    name: "Michael Paonam",
    role: "Lead · Architecture",
    bio: "Agent pipeline design, Dynatrace integration, hackathon strategy.",
    email: "mazdaswift@gmail.com",
    github: "https://github.com/MichaelPaonam",
  },
  {
    name: "Ashiha Maheshkumar",
    role: "Engineering · Attacks",
    bio: "A1/A2 attack staging, Feature Agent pipeline, Cloud Run deployment.",
    email: "ashihamaheshkumar@gmail.com",
    github: "https://github.com/ashihams",
  },
  {
    name: "Moris Takhellambam",
    role: "Engineering · Agents",
    bio: "Research Agent, Feature Agent tooling, ADK CLI integration, file-creation tools.",
    email: "moris.takhel@gmail.com",
    github: "https://github.com/MorisTakhellambam",
  },
];

export function Team() {
  return (
    <section class="section" id="team">
      <div class="container">
        <p class="section__label">Operators</p>
        <h2 class="section__title">Team</h2>
        <p class="section__lead">
          SentinelDS — securing agentic data-science workflows for the Google Cloud
          × Dynatrace hackathon.
        </p>

        <div class="team__grid">
          {TEAM.map((member) => (
            <article key={member.name} class="card cyber-chamfer team__member">
              <h3 class="team__name">
                {member.github ? (
                  <a href={member.github} target="_blank" rel="noreferrer">
                    {member.name}
                  </a>
                ) : (
                  member.name
                )}
              </h3>
              <p class="team__role">{member.role}</p>
              {member.email && (
                <a class="team__email" href={`mailto:${member.email}`}>
                  {member.email}
                </a>
              )}
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
        </p>
        <ul class="footer__links">
          <li>
            <a href="https://github.com/MichaelPaonam/sentinelds" target="_blank" rel="noreferrer">
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
