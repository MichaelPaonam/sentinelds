import "./TechStack.css";

const STACK = [
  { name: "Google ADK", role: "Agent orchestration" },
  { name: "Gemini 2.5", role: "LLM backbone" },
  { name: "Vertex AI", role: "Cloud runtime" },
  { name: "Dynatrace", role: "OTel ingest + Davis AI" },
  { name: "OpenTelemetry", role: "Span instrumentation" },
  { name: "Sentinel Agent", role: "MCP pre-flight gate" },
  { name: "FastAPI", role: "Attack server" },
  { name: "XGBoost", role: "Modelling pipeline" },
  { name: "Preact + Vite", role: "This page" },
];

const PIPELINE = [
  "Research Agent",
  "→",
  "Feature Agent",
  "→",
  "Modelling Agent",
  "→",
  "Sentinel HALT",
];

export function TechStack() {
  return (
    <section class="section section--skew" id="tech">
      <div class="container">
        <p class="section__label">Architecture</p>
        <h2 class="section__title">Tech Stack</h2>
        <p class="section__lead">
          Built for the Google Cloud Agent Builder hackathon — Gemini-powered agents,
          Dynatrace observability, and a deterministic security gate.
        </p>

        <div class="tech__grid">
          {STACK.map((item) => (
            <div key={item.name} class="tech__item cyber-chamfer-sm">
              <p class="tech__name">{item.name}</p>
              <p class="tech__role">{item.role}</p>
            </div>
          ))}
        </div>

        <div class="tech__pipeline" aria-label="Agent pipeline">
          {PIPELINE.map((part, i) =>
            part === "→" ? (
              <span key={`arrow-${i}`} class="arrow" aria-hidden="true">
                →
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
