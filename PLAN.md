# SentinelDS — Technical Plan

**Project:** Securing an agentic data-science workspace with Dynatrace
**Hackathon:** Google Cloud Rapid Agent Hackathon ([devpost](https://rapid-agent.devpost.com))
**Partner:** Dynatrace (via MCP)
**Submission deadline:** 2026-06-11 (2:00 PM PDT)
**Plan written:** 2026-05-25 | **Updated:** 2026-05-26
**Days remaining:** ~16

---

## 0. Hackathon Rules & Constraints (from Resources + FAQ)

> **These are non-negotiable.** Violating any of these risks disqualification.

### Mandatory architecture requirements
1. **Powered by Gemini** — all LLM calls must use Gemini models.
2. **Built within Google Cloud Agent Builder ecosystem** — two valid paths:
   - **Visual path:** Agent Builder UI console (low-code)
   - **Code-first path:** Agent Development Kit (ADK) — scaffold, configure, and orchestrate agents via ADK SDK/CLI and deploy to Agent Runtime / Cloud Run
3. **Integrate at least one partner MCP server** — we use **Dynatrace MCP**.

### What's restricted
- **LangChain, LangGraph, LlamaIndex cannot be your primary orchestrator.** Agent Builder / ADK must be the orchestrator. *(This settles our Day 1 decision — ADK is the only choice.)*
- **AI coding tools:** Only Google Cloud AI tools (Gemini, Agent Builder) and partner AI features are permitted. Claude, Cursor, GitHub Copilot are **NOT permitted** — not even for development workflow. **Google AntiGravity is permitted.**
- **Existing code:** Project must be newly created from scratch during contest period (May 5 – Jun 11, 2026). Reusing old codebases is not allowed; new iteration of an old idea is fine.

### Submission rules
- Each submission enters **one track only** (we enter Dynatrace track).
- A single submission can win **one prize maximum**.
- Project URL must be accessible to judges **without login** (no-login sandbox demo with preloaded sample data is acceptable).
- Demo video must clearly capture the agent functioning.

### Dynatrace track specifics
- No sample data provided — use **synthetic telemetry logs, public APM datasets, or local server log outputs**.
- Judging evaluates **autonomous agent functionality**, not data science model accuracy.
- A small, hyper-realistic dataset demonstrating clear multi-step agent reasoning beats a massive generic one.

### Billing & credits
- Google Cloud credits ($100) cover ONLY native GCP services (Vertex AI, Gemini APIs, Cloud Run, Secret Manager, Agent Builder, etc.).
- Dynatrace credits/trials are accessed independently via the Dynatrace partner resources page.
- Set up a **budget alert** in GCP Console → Billing → Budgets & alerts.
- Clean up daily: delete/pause Cloud Run services, Agent Builder instances when not building.

---

## 1. Premise

### The story: from "as-is" to "to-be"

A team of data scientists is building a **Truck Driver Drowsiness Detection** system to prevent road accidents. Today, they work in a conventional, manual workflow — Jupyter notebooks, shared CSV files, ad-hoc model training. This is the **"as-is" process**: effective but slow, unobservable, and vulnerable.

**SentinelDS** is the **"to-be" process** — the same drowsiness-detection mission, but now orchestrated by three specialist AI agents:

- **Research Agent** — surveys papers, blog posts, docs to summarize the drowsiness-detection problem space (e.g., EEG vs. camera-based approaches, fatigue biomarkers, regulatory standards).
- **Data + Feature Engineering Agent** — pulls drowsiness datasets (driver video frames, sensor readings), profiles them, builds features (eye-aspect ratio, yawn frequency, head-pose angles).
- **Modelling Agent** — selects models (CNN, LSTM, ensemble classifiers), runs hyperparameter tuning, reports metrics (accuracy, false-negative rate — critical for safety).

These agents are useful precisely because they have tools (web fetch, file/dataset access, code execution, model registries). That same surface is what attackers target. We use Dynatrace as the workspace's **immune system**: it observes every agent action, Davis AI flags anomalies, and a **Sentinel Agent** queries Dynatrace over MCP before risky actions — closing the loop from detection to response.

The demo narrative: *"Here's how a team works today (as-is). Here's how agents accelerate it (to-be). And here's what happens when those agents get attacked — and how SentinelDS stops it."*

---

### 1.1. Companion Project: "As-Is" Data Science Workspace

> **Repo:** separate repository (e.g., `drowsiness-detection-workspace`)
> **Purpose:** reference baseline that shows the manual, human-driven DS workflow SentinelDS replaces

This is a **small, self-contained** conventional data-science project. It does NOT use AI agents. It exists to:
1. Provide a **concrete, relatable problem domain** (truck driver safety) that makes the demo compelling.
2. Serve as the **source of realistic artifacts** (datasets, notebooks, model files) that the SentinelDS agents will operate on.
3. Create a **before/after contrast** for the demo video and submission writeup.

#### What the companion repo contains

| Component | Description | Files |
|-----------|-------------|-------|
| **Research notes** | Manual literature survey on drowsiness detection methods | `research/notes.md`, `research/papers.bib` |
| **Dataset** | Small sample dataset — driver face images or sensor readings with drowsy/alert labels | `data/raw/sample_frames.csv` or image folder |
| **EDA notebook** | Exploratory data analysis — class distribution, feature distributions, missing values | `notebooks/01_eda.ipynb` |
| **Feature engineering** | Manual feature extraction — eye-aspect ratio, yawn count, head-pose angles | `notebooks/02_features.ipynb`, `src/features.py` |
| **Model training** | Baseline model (e.g., Random Forest or simple CNN) with train/eval split | `notebooks/03_model.ipynb`, `src/train.py` |
| **Results** | Metrics, confusion matrix, a brief report | `results/metrics.json`, `results/report.md` |

#### What it deliberately lacks (the "as-is" gaps SentinelDS fills)

- ❌ **No observability** — no tracing, no telemetry, no audit trail of who ran what when
- ❌ **No anomaly detection** — a poisoned CSV goes unnoticed; a malicious URL in research notes gets fetched blindly
- ❌ **No automated pipeline** — every step is manual notebook execution
- ❌ **No security guardrails** — no pre-flight checks on data sources, no egress monitoring

#### Scope guard

This is a **throwaway reference project**, not a production ML system. Keep it minimal:
- Use a small public dataset (e.g., [UTA-RLDD](https://www.kaggle.com/datasets) or [Driver Drowsiness Dataset](https://www.kaggle.com/datasets/ismailnasri20/driver-drowsiness-dataset-ddd) on Kaggle, or synthetic data)
- The model does NOT need to be good — it just needs to be plausible
- Total effort: **~2–3 hours** to scaffold, tops
- The companion repo is NOT submitted to the hackathon — it's supporting material referenced in the SentinelDS demo

---

## 2. Threat model (scoped for demo)

We threat-modelled five realistic attacks (full list at the bottom of this doc). For the hackathon we demo **two**, end-to-end:

| # | Attack | Target agent | Why it's the right demo |
|---|--------|--------------|-------------------------|
| **A1** | **Indirect prompt injection** — malicious instructions hidden in a fetched webpage tell the agent to exfiltrate the dataset. | Research Agent | #1 real-world agent threat in 2026; visually compelling; defended by behavior anomaly + egress detection. |
| **A2** | **Data poisoning** — crafted rows in an ingested CSV (label flips + a trigger pattern) skew the trained model. | Feature Engineering Agent | Classic ML attack; defended by data-drift / statistical anomaly signals from Dynatrace. |

The "wow" moment: the **Sentinel Agent** notices Davis AI has flagged the workspace, queries Dynatrace via MCP, and **halts the next tool call** before damage spreads.

---

## 3. Architecture

```
+-----------------------------------------------------------------------+
|                       SentinelDS Workspace                            |
|                   (Google Cloud Agent Builder / ADK)                   |
|                                                                       |
|  +---------------+   +-------------------+   +-------------------+    |
|  |  Research     |   |  Feature Eng.     |   |    Modelling      |    |
|  |  Agent        |   |  Agent            |   |    Agent          |    |
|  | (Gemini /     |   | (Gemini /         |   | (Gemini /         |    |
|  |  ADK)         |   |  ADK)             |   |  ADK)             |    |
|  +-------+-------+   +---------+---------+   +---------+---------+    |
|          |                     |                       |              |
|          | tool calls (web,    | tool calls (pandas,   | tool calls   |
|          |  fetch, search)     |  duckdb, sklearn)     | (sklearn,    |
|          v                     v                       v   optuna)    |
|  +---------------------------------------------------------------+    |
|  |          OpenTelemetry instrumentation layer                  |    |
|  |  (LLM spans, tool spans, MCP spans, dataset I/O attributes)   |    |
|  +-----------------------------+---------------------------------+    |
|                                |                                      |
|                                | OTLP                                 |
|                                v                                      |
|  +---------------------------------------------------------------+    |
|  |                      Dynatrace SaaS                           |    |
|  |  - Distributed traces  - Davis AI anomaly detection           |    |
|  |  - Logs / events       - Security signals (egress, RCE)       |    |
|  +-----------------------------+---------------------------------+    |
|                                ^                                      |
|                                | MCP query (problems, events,         |
|                                |  DQL on spans)                       |
|                                |                                      |
|  +-----------------------------+---------------------------------+    |
|  |                     Sentinel Agent                            |    |
|  |  - Polls Dynatrace MCP for active problems on the workspace   |    |
|  |  - Pre-flight check before risky tool calls                   |    |
|  |  - Decision: ALLOW | WARN | HALT (+ quarantine)               |    |
|  +---------------------------------------------------------------+    |
+-----------------------------------------------------------------------+

Deployment: ADK → Agent Runtime / Cloud Run (GCP)
Demo: No-login sandbox with preloaded synthetic telemetry data

Attack surfaces (red):
   A1: Research Agent fetches malicious page  --> prompt-injection payload
   A2: Feature Eng. Agent reads poisoned CSV  --> drift/label-flip payload
```

**Key flows**

1. **Normal operation** — agent invokes a tool; the call is wrapped in an OTel span with attributes (`tool.name`, `tool.args.hash`, `dataset.uri`, `egress.host`). Spans flow to Dynatrace.
2. **Detection** — Davis AI auto-baselines and raises a problem when (a) outbound traffic goes to an unseen host, (b) an LLM prompt contains injection signatures, or (c) ingested-data statistics drift beyond threshold.
3. **Response** — Sentinel Agent's pre-flight check calls the Dynatrace MCP (`list_problems`, `execute_dql`) before each risky tool call. If a problem matches the active workspace, Sentinel returns `HALT` and the orchestrator skips the call.

---

## 4. Pre-requisites

### Accounts & access
- [x] Dynatrace tenant + MCP server access (confirmed)
- [x] Google Cloud project with Vertex AI / Gemini API enabled
- [x] Devpost registration for the hackathon
- [x] GitHub repo for submission (public)
- [ ] Google Cloud credits ($100) claimed and visible in Billing → Credits
- [ ] Budget alert configured in GCP Console ($0 hard limit)

### Local toolchain
- Python 3.11+, `uv` or `poetry`
- `gcloud` CLI authenticated
- Node.js 20+ (for any MCP tooling)
- Docker (for reproducible workspace + optional sandboxing)
- **Google AntiGravity** (permitted AI dev tool)

### Python packages (initial)
- **Agents:** `google-adk` (Agent Development Kit) — **mandatory per hackathon rules**
- **MCP client:** `mcp` (official Python SDK)
- **Observability:** `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-requests`
- **DS stack:** `pandas`, `duckdb`, `scikit-learn`, `optuna`
- **LLM tracing:** `openllmetry` (Traceloop) — gives free LLM/tool spans

### Dynatrace setup
- OTLP ingest endpoint + API token with `openTelemetryTrace.ingest`, `metrics.ingest`, `logs.ingest`
- MCP server endpoint + token with `problems.read`, `entities.read`, `DataExport`
- A Notebook or Dashboard pre-seeded for the demo

### What we're explicitly NOT building
- Real authentication / multi-tenant workspace
- A polished UI — a CLI + a single Dynatrace dashboard is enough (but project URL must work without login for judges)
- Production-grade sandboxing of agent tool execution

---

## 5. Official Resources (from hackathon Resources page)

### Phase 1: Core Frameworks & Environment
- [Gemini Enterprise Agent Platform API Setup](https://console.cloud.google.com/) — mission control for all GCP agent projects
- [Agent Builder Guide](https://cloud.google.com/products/agent-builder) — low-code path with managed orchestration, grounding, data stores
- [Gemini Enterprise Agent Platform SDK for Python](https://cloud.google.com/python/docs/reference/aiplatform/latest) — client library for custom agent logic and tool calls
- [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack)
- GCP access: [Free trial](https://cloud.google.com/free) or [request $100 credits](https://forms.gle/xfv9vQzfRfNCCVbG7) (limited, first-come-first-served)

### Phase 2: Action Mechanisms & Data Connectivity
- [Building & Managing Extensions](https://cloud.google.com/vertex-ai/docs/generative-ai/extensions/overview) — pre-built Google extensions or connect to external APIs
- [Agent Search and Agent Conversation Overview](https://cloud.google.com/vertex-ai/docs/generative-ai/agent-builder/overview) — index PDFs, websites, BigQuery tables for grounding

### Phase 3: Partner Integration (Dynatrace)
- [Dynatrace resources page](https://rapid-agent.devpost.com/details/dynatrace-resources) — partner-specific setup and MCP server details

### Phase 4: Reasoning, State & Logic Hosting
- [Agent Runtime](https://cloud.google.com/vertex-ai/docs/generative-ai/reasoning-engine/overview) — runtime for deploying Python-based agents
- [Secret Manager](https://cloud.google.com/secret-manager) — securely store API keys for partner integrations

### Phase 5: Deployment & Safety
- [Cloud Run Quickstart](https://cloud.google.com/run/docs/quickstarts) — hosting agent backends or custom tool servers
- [Gemini Enterprise Agent Platform Safety Settings](https://cloud.google.com/vertex-ai/docs/generative-ai/learn/responsible-ai) — configure guardrails

---

## 6. Topics to study (front-load Days 1–3)

### Must-read / must-watch
1. **Google ADK (Agent Development Kit)** quickstart + multi-agent example — **this is our mandatory orchestrator**. No fallback to LangGraph.
2. **Dynatrace AI Observability** — how OTel traces from LLM apps surface in Dynatrace; the "AI & LLM Observability" docs.
3. **Dynatrace MCP server** — available tools, auth model, response shapes. Spend an hour calling each tool from a notebook before designing the Sentinel Agent.
4. **Davis AI problem detection** — how baselines form, how to seed custom events, how problem IDs map to entities.
5. **OpenLLMetry / Traceloop** — drops in OTel instrumentation for LLM + tool calls with one line; saves a day of work.
6. **Agent Builder UI (Studio)** — understand the visual path; even if we go code-first with ADK, knowing the console helps debugging.

### Threat-modelling references
- OWASP Top 10 for LLM Applications (2025) — especially LLM01 (prompt injection) and LLM03 (training data poisoning)
- MITRE ATLAS — tactics for ML systems
- Simon Willison's writeups on indirect prompt injection (concrete payload examples)

### Decisions now locked (per FAQ rules)
- ~~ADK vs LangGraph~~ → **ADK is mandatory** (LangGraph cannot be primary orchestrator)
- Gemini model tier: Flash for cost during dev, Pro for demo
- LLM trace exporter: OpenLLMetry (try first) vs hand-rolled
- Sentinel Agent runs as in-process supervisor via ADK multi-agent orchestration
- **AI coding assistant: Google AntiGravity only** (Claude, Cursor, Copilot not permitted)

---

## 7. Day-by-day breakdown

~16 days remaining, treated as **3 phases**: Foundation (Days 1–6), Attack & Defense (7–12), Polish & Submit (13–17). Each day lists *outcome* — what exists at end of day — not hours.

### Phase 1 — Foundation (Days 1–6)

| Day | Date | Outcome |
|-----|------|---------|
| 1 | Mon May 26 | **Companion repo** (`drowsiness-detection-workspace`) scaffolded with sample dataset, EDA notebook, and baseline model. SentinelDS repo scaffolded; ADK confirmed as orchestrator (per rules); `uv` env; Gemini "hello world" runs via ADK; Dynatrace OTLP token validated by sending one manual span. GCP credits claimed + budget alert set. |
| 2 | Tue May 27 | Research Agent v0 — single ADK agent, web fetch tool, returns a summary. Spans appear in Dynatrace. OpenLLMetry wired. |
| 3 | Wed May 28 | Feature Eng. Agent v0 + Modelling Agent v0 (skeletons). ADK orchestrator routes a request across all three. End-to-end trace visible in Dynatrace. |
| 4 | Thu May 29 | Dynatrace MCP client wired. Sentinel Agent v0 can call `list_problems`, `execute_dql` and print results. |
| 5 | Fri May 30 | Sentinel Agent integrated as pre-flight check — every tool call routed through it. Default policy: ALLOW. |
| 6 | Sat May 31 | **Milestone M1: Happy path works end-to-end and is fully observable.** A user request flows through 3 agents, Sentinel pre-checks each tool call, full trace visible in Dynatrace. No attacks yet. |

### Phase 2 — Attack & Defense (Days 7–12)

| Day | Date | Outcome |
|-----|------|---------|
| 7 | Sun Jun 1 | **A1 attack staged** — a local "malicious" webpage with embedded prompt injection; Research Agent visibly compromised (tries to call exfil tool). |
| 8 | Mon Jun 2 | A1 detection — emit a custom Dynatrace event when LLM input matches injection heuristics; Davis AI raises a problem. Verify problem appears via MCP. |
| 9 | Tue Jun 3 | A1 defense — Sentinel queries problems pre-flight, returns HALT, orchestrator quarantines the agent. End-to-end attack→detection→halt demo works. |
| 10 | Wed Jun 4 | **A2 attack staged** — poisoned CSV with label flips; Feature Eng. Agent ingests it; downstream model accuracy drops. |
| 11 | Thu Jun 5 | A2 detection + defense — emit dataset-stats metrics; Davis AI flags drift; Sentinel halts modelling step. |
| 12 | Fri Jun 6 | **Milestone M2: Both attack scenarios run end-to-end with detection and response.** Lock the demo script. |

### Phase 3 — Polish & Submit (Days 13–17)

| Day | Date | Outcome |
|-----|------|---------|
| 13 | Sat Jun 7 | Dynatrace dashboard built: workspace overview, agent activity, problem timeline. No-login sandbox demo URL for judges. |
| 14 | Sun Jun 8 | Demo script rehearsed; CLI UX cleaned up; README v1 written. Ensure project URL works without login. |
| 15 | Mon Jun 9 | **Milestone M3: Demo video recorded** (3 min, both attacks, narrated). Re-record if rough. |
| 16 | Tue Jun 10 | Buffer day — fix anything embarrassing; tighten README; architecture diagram exported as image. |
| 17 | Wed Jun 11 | Final submission package: repo, video, devpost write-up, architecture diagram. **Submit at least 4h before deadline (2:00 PM PDT).** |

### Milestones summary

- **M1 (Sat May 31):** observable happy path
- **M2 (Fri Jun 6):** both attacks demoed end-to-end
- **M3 (Mon Jun 9):** demo video in the can
- **Submission:** Wed Jun 11 (submit by morning, deadline is 2:00 PM PDT)

If M1 slips past Jun 1, drop A2 and demo A1 only. If M2 slips past Jun 8, skip the dashboard polish. **Do not compromise on M3** — a hackathon submission without a working video underperforms a working video with rougher code.

---

## 8. Risks & mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| ADK's multi-agent orchestration has rough edges | Medium | No fallback to LangGraph (rules prohibit it). Mitigate by reading every ADK example + Agent Starter Pack. If multi-agent is too unstable, use sequential single-agent calls orchestrated by a thin ADK wrapper. |
| Dynatrace MCP tools don't expose what we need (e.g., no per-entity problem feed) | Medium | Day 1 spike: call every MCP tool, document responses. Fall back to direct Dynatrace API if MCP is thin. |
| Davis AI doesn't auto-detect our staged anomalies in time for demo | High | Don't rely on auto-detection alone — emit explicit custom events; Davis correlates them into problems quickly. |
| Demo flakes live (network, rate limits) | High | Record the video against a stable replay; never demo live for the submission. |
| Scope creep into "real" sandboxing or auth | High | This plan explicitly excludes them; revisit only post-M2. |
| Accidentally using non-permitted AI tools during dev | Medium | Remove Claude/Cursor/Copilot from IDE. Use only AntiGravity for AI-assisted coding. |
| GCP credits run out before submission | Medium | Set hard budget alert. Use Gemini Flash during dev, Pro only for final demo. Clean up Cloud Run daily. |
| Project URL not accessible to judges | Medium | Build a no-login sandbox demo with preloaded sample data. Test access from an incognito browser. |

---

## 9. Full threat list (for the writeup, not the demo)

For completeness in the submission narrative — we'll mention these as future work:

1. **Indirect prompt injection** (A1, demoed)
2. **Data poisoning** (A2, demoed)
3. **Tool / MCP abuse** — agent tricked into calling destructive tools
4. **Model supply-chain poisoning** — malicious pre-trained model from a registry
5. **Resource abuse / cryptojacking** — compromised agent spawns miners during "tuning"
6. **Secret exfiltration** — agent reads env vars / credentials and sends them out
7. **Recursive agent loops** — DoS via runaway agent-to-agent calls

---

## 10. Open questions to resolve in Day 1

- ~~ADK or LangGraph?~~ → **ADK (mandatory per rules)**
- Where does the Sentinel Agent's policy live — code, or a Dynatrace-managed config?
- For the demo, do we replay a recorded trace or run live? (Bias: live for M2, recorded for the video.)
- Single-machine demo or deploy to Cloud Run? (Bias: Cloud Run for the final submission, local for dev.)
- How to build the no-login sandbox demo URL for judges?
- What synthetic telemetry data to use for the Dynatrace track demo?
