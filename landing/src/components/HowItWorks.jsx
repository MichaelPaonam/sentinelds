import "./HowItWorks.css";

const STEPS = [
  {
    num: "01",
    title: "Emit",
    desc: "Every LLM call and tool invocation ships OpenTelemetry spans — works with the agent frameworks you already use.",
  },
  {
    num: "02",
    title: "Detect",
    desc: "Custom detectors flag prompt injection, label drift, and anomalous egress. Davis AI surfaces the rest.",
  },
  {
    num: "03",
    title: "Decide",
    desc: "The Sentinel policy engine evaluates context in real time and returns ALLOW, WARN, or HALT — in milliseconds.",
  },
  {
    num: "04",
    title: "Enforce",
    desc: "Risky tool calls are blocked at the boundary. Audit trails are preserved. Your agents stay productive.",
  },
];

export function HowItWorks() {
  return (
    <section class="section section--skew" id="how-it-works">
      <div class="container">
        <p class="section__label">The Defense Loop</p>
        <h2 class="section__title">How It Works</h2>
        <p class="section__lead">
          SentinelDS sits beside every agent and inspects every tool call.
          Threats become visible in telemetry before they become incidents —
          no SDK rewrite, no agent redesign.
        </p>

        <div class="how__steps">
          {STEPS.map((step) => (
            <article key={step.num} class="card cyber-chamfer">
              <p class="how__step-num">{step.num}</p>
              <h3 class="how__step-title">{step.title}</h3>
              <p class="how__step-desc">{step.desc}</p>
            </article>
          ))}
        </div>

        <div class="card card--terminal cyber-chamfer how__terminal">
          <p class="terminal-line terminal-line--accent">sentinel.preflight(tool="web_fetch")</p>
          <p class="terminal-line">  ↳ context_signals: injection_score=0.91, egress_anomaly=true</p>
          <p class="terminal-line terminal-line--warn">  ↳ verdict: HALT — blocked at tool boundary</p>
          <p class="terminal-line terminal-line--accent">  ↳ audit_event: emitted to your observability backend</p>
        </div>
      </div>
    </section>
  );
}
