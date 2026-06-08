# SentinelDS

> **Dynatrace as the AI agent immune system.** Every agent action is observed, anomalies become Problems, and a Sentinel Agent halts the next risky tool call before damage spreads.

An agentic data-science workspace defended by Dynatrace, submitted to the [Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com) — partner: **Dynatrace** (via MCP). Submission deadline: **2026-06-11 12:00 PDT**.

---

## What it is

Three specialist agents collaborate on a real data-science mission — building a **truck-driver drowsiness-detection** model from EEG, video, and sensor data:

- **Research Agent** — surveys papers and blog posts; summarizes the problem space (EEG vs camera-based approaches, fatigue biomarkers, regulatory standards).
- **Feature Engineering Agent** — pulls drowsiness datasets, profiles them, builds features (eye-aspect ratio, yawn frequency, head-pose angles).
- **Modelling Agent** — selects models, runs hyperparameter tuning, reports metrics with a focus on false-negative rate (safety-critical).

Every LLM call, tool call, and dataset I/O is wrapped in OpenTelemetry and shipped to **Dynatrace SaaS**. **Davis AI** baselines the workspace and raises Problems on anomalous behavior. A separate **Sentinel Agent** queries Dynatrace over the **MCP** before each risky tool call and decides **ALLOW / WARN / HALT** — a deterministic, fail-closed gate that catches what model-layer safety tuning cannot.

## What we're demonstrating

Two attacks, end-to-end, with detection and Sentinel response:

| Attack | Target | What it exploits | What stops it |
|---|---|---|---|
| **A1 — Indirect prompt injection** | Research Agent (`lit_fetcher`) | Trusted paper source embeds malicious callback URLs as `supplementary_data_url` and `references[]` — agent chases them because its own prompt instructs enrichment via cited sources | Custom event on injection signature → Davis Problem → Sentinel HALT on next risky call |
| **A2 — Data poisoning** | Feature Engineering Agent (CSV ingest) | Poisoned CSV (label flips + trigger pattern) reaches training | `dataset.stats.*` drift metrics → Davis Problem → Sentinel HALT at training boundary, dataset SHA-256 quarantined |

Five additional threats (tool/MCP abuse, model supply-chain poisoning, resource abuse, secret exfiltration, recursive agent loops) are catalogued in [`PLAN.md` section 9](PLAN.md) as future work.

### Why the attacks succeed against a hardened Gemini

Both attacks exploit the **agent architecture**, not the model:

- **A1** works because the Research Agent is *instructed* to fetch web pages and enrich its findings with referenced supplementary and replication URLs. The attack payload contains no imperative directive — malicious URLs are embedded as normal research-apparatus fields (`supplementary_data_url`, `references[]`). The agent follows them because its own prompt tells it to chase cited sources. Confirmed working end-to-end against Gemini 2.5 Flash Lite.
- **A2** never touches the LLM — the poisoned CSV flows through `csv_read` → `pandas_profile` → training. Model alignment is irrelevant; the attack is on the data pipeline.

This is the **point**: model-layer safety is necessary but insufficient for agentic systems. The attack surface is the agent's tools and data flow. SentinelDS defends at the architectural layer, where the actual exposure lives. This matches the SANS AISMM Stage 4 *Confused Deputy* framing — a legitimately permissioned, well-aligned agent manipulated through trusted inputs.

## The defense loop

Every demoed attack follows the same four-phase loop. This is the architectural claim of the project:

```mermaid
flowchart LR
    E["<b>1. EMIT</b>\nOTel spans + custom events\nfrom every tool call"]
    D["<b>2. DETECT</b>\nDavis AI + custom event\ncorrelation raises a Problem"]
    De["<b>3. DECIDE</b>\nSentinel Agent queries MCP,\nreturns ALLOW / WARN / HALT\n(deterministic)"]
    En["<b>4. ENFORCE</b>\nOrchestrator skips tool call;\nquarantines agent / dataset"]

    E --> D --> De --> En
```

Sentinel's decision is **deterministic** (rule-based on Problem state, not LLM-decided) and **fail-closed** (MCP unreachable → HALT for training/egress). A prompt-injected agent cannot talk Sentinel out of halting.

## Maturity claim

SentinelDS demonstrates **SANS AISMM Stage 3 → 4 capabilities** for the workspace it observes:

- **Stage 3 fully present** — AI inventory (three named agents), structured trace IDs across agent steps and tool calls, prompt-injection defenses, ATLAS-mapped controls (AML.T0051, AML.T0020), input validation
- **Stage 4 partially present** — execution guardrails on agent API calls, Confused Deputy defense, MLSecOps training-data validation, controls for cascading failures (quarantine stops propagation)

Out of scope for the hackathon: governance artifacts (AI Governance Council, NHI lifecycle, board-level risk reporting), full red-teaming program, quantitative risk methodology. See [`docs/ai-security-threat-modelling.md`](docs/ai-security-threat-modelling.md) for the complete maturity-stage mapping.

---

## Architecture

```mermaid
flowchart TD
    subgraph workspace["SentinelDS Workspace (Google Cloud / ADK)"]
        direction TB

        subgraph agents["Three Gemini Agents"]
            direction LR
            RA["Research Agent\nlit_searcher · lit_fetcher"]
            FA["Feature Eng Agent\ndataset_profiler · feature_transformer"]
            MA["Modelling Agent\nXGBoost · CatBoost · reporter"]
        end

        OTel["OpenTelemetry Layer\nLLM · tool · MCP · I/O spans"]

        RA -- tool calls --> OTel
        FA -- tool calls --> OTel
        MA -- tool calls --> OTel
    end

    OTel -- "OTLP/HTTP" --> DT

    subgraph dynatrace["Dynatrace SaaS"]
        DT["Traces · Davis AI · Problems"]
    end

    DT -- "MCP (list_problems, execute_dql)" --> SA

    SA["Sentinel Agent\nALLOW / WARN / HALT"]
    SA -. "pre-flight decision" .-> agents
```

Full architecture, including span-attribute schemas and trust boundaries, is in [`docs/ai-security-threat-modelling.md`](docs/ai-security-threat-modelling.md) sections 6–7.

---

## Repo layout

```
sentinelds/
├── README.md                                  ← this file
├── PLAN.md                                    ← technical plan, schedule, milestones
├── docs/
│   ├── ai-security-threat-modelling.md        ← AISMM pillars, MITRE ATLAS, defense loop
│   ├── agents-exploit-scenarios.md            ← A1 + A2 step-by-step walkthroughs
│   ├── dynatrace-mcp-notes.md                 ← Dynatrace MCP spike: tool shapes, response schemas
│   └── dynatrace-mcp-options.md               ← MCP connectivity options and trade-offs
├── src/
│   ├── agents/
│   │   ├── agent.py                           ← root SequentialAgent (research → features → modeling)
│   │   └── sub_agents/
│   │       ├── research_agent/                ← lit_searcher + lit_fetcher (A1 target)
│   │       ├── feature_agent/                 ← dataset_profiler + feature_transformer
│   │       └── modeling_agent/                ← XGBoost + CatBoost trainer + reporter
│   ├── a2a_agents/
│   │   ├── a2a_research/                      ← research agent packaged as A2A service (Dockerfile)
│   │   ├── a2a_feature/                       ← feature agent packaged as A2A service (Dockerfile)
│   │   └── a2a_modeling/                      ← modeling agent packaged as A2A service (Dockerfile)
│   ├── attack_server/
│   │   └── server.py                          ← fake paper API with subtle A1 payload (v4)
│   ├── core/
│   │   └── config.py                          ← Pydantic Settings (env vars, model names, e2e defaults)
│   ├── e2e/
│   │   └── run_demo.py                        ← end-to-end pipeline runner CLI
│   ├── observability/
│   │   ├── otel.py                            ← TracerProvider init + OTLP/HTTP export to Dynatrace
│   │   ├── instrumentation.py                 ← once-per-process Google GenAI SDK auto-instrumentation
│   │   └── tools.py                           ← @trace_tool decorator + tool_span context manager
│   ├── sentinel/
│   │   ├── preflight.py                       ← ALLOW/WARN/HALT decision engine
│   │   └── dynatrace_mcp.py                   ← Dynatrace MCP client
│   ├── smoke/                                 ← OTel plumbing verification
│   └── tools/                                 ← fetch_url, feature_tools, modeling_tools, …
├── data/ecg_csv/                              ← raw EEG/ECG drowsiness CSVs (gitignored)
├── tests/                                     ← pytest unit tests
├── pyproject.toml                             ← Python deps (Python 3.12+, uv-managed)
└── .env.example                               ← required env vars
```

---

## Setup & development

We use [`uv`](https://github.com/astral-sh/uv) for fast Python package and environment management. Python **3.12+** required.

```bash
git clone https://github.com/MichaelPaonam/sentinelds.git
cd sentinelds

# Create + sync environment
uv venv
source .venv/bin/activate            # macOS/Linux
# .venv\Scripts\activate              # Windows

uv sync
```

### Multi-platform OpenMP Dependencies
The **Modelling Agent** uses `xgboost`, which relies on the OpenMP runtime to run. Depending on your operating system, follow the instructions below:

- **macOS (Intel/Apple Silicon)**: Run `brew install libomp` to install the OpenMP library. This is required because Mac wheels do not bundle it by default.
- **Ubuntu/Linux**: No manual installation is typically needed as `libgomp1` is pre-installed on most distributions. If you encounter any issues, install it with:
  ```bash
  sudo apt-get update && sudo apt-get install -y libgomp1
  ```
- **Windows**: The required DLL is bundled with standard Windows wheels. If you see runtime errors, make sure you have the [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/en-US/cpp/windows/latest-supported-vc-redist) installed.


### Required environment variables

Copy `.env.example` to `.env` and fill in:

```bash
# Google Cloud / Vertex AI for Gemini
GOOGLE_GENAI_USE_VERTEXAI="true"
GOOGLE_CLOUD_PROJECT="<your-gcp-project-id>"
GOOGLE_CLOUD_LOCATION="asia-southeast1"

# Dynatrace OTLP ingest (token scopes: openTelemetryTrace.ingest, metrics.ingest, logs.ingest)
DYNATRACE_API_URL="https://<your-environment-id>.live.dynatrace.com"
DYNATRACE_API_TOKEN="<your-dynatrace-api-token>"
```

`gcloud` must be authenticated to the same project. Vertex AI / Gemini APIs must be enabled.

### Verify Dynatrace OTLP plumbing

```bash
python src/smoke/dynatrace_smoke_test.py    # sends one manual span
python src/smoke/verify_smoke_test.py       # confirms it landed in the tenant
```

---

## Status & roadmap

Execution is tracked on the [GitHub project board](https://github.com/users/MichaelPaonam/projects/1), organized as three Phase Epics:

| Phase | Epic | Closes | Status |
|---|---|---|---|
| Phase 1 — Foundation | [#17](https://github.com/MichaelPaonam/sentinelds/issues/17) | M1 (observable happy path) | Complete |
| Phase 2 — Attack & Defense | [#18](https://github.com/MichaelPaonam/sentinelds/issues/18) | M2 (A1 + A2 demoed end-to-end) | A1 confirmed ✓ · OTel across all agents ✓ · A2 pending |
| Phase 3 — Polish & Submit | [#19](https://github.com/MichaelPaonam/sentinelds/issues/19) | M3 (video) → Submission | Pending |

**Slip rules** (per `PLAN.md` section 7): if M1 slips, demo A1 only; if M2 slips, skip dashboard polish; **never compromise on M3** — a working video with rougher code outperforms a polished repo without one.

---

## Hackathon compliance

- **Powered by Gemini** ✓ (`google-genai` + `google-adk`)
- **Built within Google Cloud Agent Builder ecosystem** ✓ (ADK as primary orchestrator — LangChain / LangGraph / LlamaIndex are explicitly disallowed by the rules)
- **Integrates a partner MCP server** ✓ (Dynatrace MCP)
- **Track:** Dynatrace (single-track submission)
- **AI coding tools used during development:** Google AntiGravity only (Claude / Cursor / Copilot are not permitted per hackathon rules)

---

## References

The threat-modelling and detection design draws on:

- **SANS AI Security Maturity Model™** (Chris Cochran, SANS Institute) — pillar/stage framing
- **RAI-AgentSec** — agent-shaped compliance checks (HITL, MCP Hub, tracing, audit logs)
- **OWASP Top 10 for LLM Applications (2025)** — LLM01 (prompt injection), LLM03 (training data poisoning)
- **MITRE ATLAS™** — AML.T0051 (Indirect Prompt Injection), AML.T0020 (Poison Training Data)
- **Simon Willison** — practical writeups on indirect prompt injection
- **[google/adk-samples](https://github.com/google/adk-samples)** — ADK sub-agent patterns referenced during implementation of the Research, Feature Engineering, and Modelling agents

Detailed citations in [`docs/ai-security-threat-modelling.md`](docs/ai-security-threat-modelling.md).

---

## License

MIT — see [LICENSE](LICENSE).
