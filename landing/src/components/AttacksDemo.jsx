import "./AttacksDemo.css";

const THREATS = [
  {
    id: "injection",
    code: "01",
    title: "Indirect Prompt Injection",
    badgeClass: "badge",
    cardClass: "attack-card--a1",
    target: "Web fetch · RAG retrieval · email & doc tools",
    steps: [
      { label: "Surface", text: "Hidden directives smuggled in fetched content, retrieved docs, or untrusted upstream context" },
      { label: "Risk", text: "Agents act on attacker instructions — silent exfil, unauthorized API calls, scope escalation" },
      { label: "Defense", text: "Content scored at ingest, exfil destinations vetted, suspicious tool calls halted at the boundary" },
    ],
    proof: "Blocked before the outbound request leaves your network",
  },
  {
    id: "poisoning",
    code: "02",
    title: "Data Poisoning",
    badgeClass: "badge badge--magenta",
    cardClass: "attack-card--a2",
    target: "Training data · feature pipelines · fine-tuning corpora",
    steps: [
      { label: "Surface", text: "Tampered datasets — flipped labels, backdoor triggers, distribution drift in upstream sources" },
      { label: "Risk", text: "Models train on corrupted signal — degraded accuracy, exploitable backdoors, silent failure in production" },
      { label: "Defense", text: "Statistical drift caught at ingest, suspect data quarantined, training halted before compute is spent" },
    ],
    proof: "Model integrity preserved — training runs on verified data only",
  },
];

export function AttacksDemo() {
  return (
    <section class="section" id="threats">
      <div class="container">
        <p class="section__label">What We Catch</p>
        <h2 class="section__title">Threats We Neutralize</h2>
        <p class="section__lead">
          From the prompt that reaches your agent to the data that trains your
          model — SentinelDS guards the full agentic surface. Two of the most
          consequential threat classes, both shut down by the same loop.
        </p>

        <div class="attacks__layout">
          <div class="attacks__grid">
            {THREATS.map((threat) => (
              <article
                key={threat.id}
                class={`card cyber-chamfer attack-card ${threat.cardClass}`}
              >
                <div class="attack-card__header">
                  <h3 class="attack-card__title">{threat.title}</h3>
                  <span class={threat.badgeClass}>{threat.code}</span>
                </div>
                <p class="attack-card__target">Surface: {threat.target}</p>
                <ul class="attack-card__list">
                  {threat.steps.map((step) => (
                    <li key={step.label}>
                      <strong>{step.label}:</strong> {step.text}
                    </li>
                  ))}
                </ul>
                <p class="attack-card__proof">{threat.proof}</p>
              </article>
            ))}
          </div>

          <div class="card card--terminal cyber-chamfer attacks__terminal">
            <p class="terminal-line terminal-line--accent">
              [sentinel] tool_call intercepted: agent=research, tool=web_fetch
            </p>
            <p class="terminal-line">
              [sentinel] policy_check: egress_destination outside allowlist
            </p>
            <p class="terminal-line terminal-line--warn">
              [sentinel] verdict=HALT · agent notified · audit event emitted
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
