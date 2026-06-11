import "./TechStack.css";

const STACK = [
  { name: "OpenTelemetry", role: "Open standard for span ingest" },
  { name: "Dynatrace", role: "Davis AI + policy backbone" },
  { name: "Google ADK", role: "Native agent integration" },
  { name: "Gemini on Vertex AI", role: "Reasoning over tool intent" },
  { name: "Cloud Run", role: "Containerized deployment surface" },
  { name: "Your Stack", role: "Framework-agnostic by design" },
];

const FLOW = [
  "Your Agents",
  "⇄",
  "Sentinel Gate",
  "⇄",
  "Your Tools",
];

export function TechStack() {
  return (
    <section class="section section--skew" id="tech">
      <div class="container">
        <p class="section__label">Built On Open Standards</p>
        <h2 class="section__title">Works With Your Stack</h2>
        <p class="section__lead">
          SentinelDS is observability-native. If your agents emit OpenTelemetry,
          you're already half-deployed — no proprietary SDK, no rewrite, no
          vendor lock on the agent side.
        </p>

        <div class="tech__grid">
          {STACK.map((item) => (
            <div key={item.name} class="tech__item cyber-chamfer-sm">
              <p class="tech__name">{item.name}</p>
              <p class="tech__role">{item.role}</p>
            </div>
          ))}
        </div>

        <div class="tech__pipeline" aria-label="Sentinel sits at the tool boundary">
          {FLOW.map((part, i) =>
            part === "⇄" ? (
              <span key={`arrow-${i}`} class="arrow" aria-hidden="true">
                ⇄
              </span>
            ) : (
              <span key={part} class="cyber-chamfer-sm">
                {part}
              </span>
            ),
          )}
        </div>
      </div>
    </section>
  );
}
