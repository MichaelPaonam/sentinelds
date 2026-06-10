import "./HowItWorks.css";

const STEPS = [
  {
    num: "01",
    title: "Emit",
    desc: "Every LLM call and tool invocation ships OpenTelemetry spans to Dynatrace.",
  },
  {
    num: "02",
    title: "Detect",
    desc: "Davis AI baselines the workspace and raises Problems on anomalous egress or drift.",
  },
  {
    num: "03",
    title: "Decide",
    desc: "The Sentinel Agent queries Dynatrace MCP and returns ALLOW, WARN, or HALT.",
  },
  {
    num: "04",
    title: "Enforce",
    desc: "The orchestrator blocks risky tool calls — exfil, training on poisoned data.",
  },
];

export function HowItWorks() {
  return (
    <section class="section section--skew" id="how-it-works">
      <div class="container">
        <p class="section__label">Defense Loop</p>
        <h2 class="section__title">How It Works</h2>
        <p class="section__lead">
          SentinelDS wraps a multi-agent data-science pipeline with observability-first
          security. Attacks become visible in telemetry before they become incidents.
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
          <p class="terminal-line terminal-line--accent">sentinel.preflight("web_fetch")</p>
          <p class="terminal-line">problems = dynatrace.list_problems(workspace_id)</p>
          <p class="terminal-line terminal-line--warn">if injection_detected: return HALT</p>
          <p class="terminal-line terminal-line--accent">verdict = ALLOW → proceed with fetch</p>
        </div>
      </div>
    </section>
  );
}
