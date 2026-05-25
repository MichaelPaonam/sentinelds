# SentinelDS — Technical Plan

**Project:** Securing an agentic data-science workspace with Dynatrace
**Hackathon:** Google Cloud Rapid Agent Hackathon ([devpost](https://rapid-agent.devpost.com))
**Partner:** Dynatrace (via MCP)
**Submission deadline:** 2026-06-11
**Plan written:** 2026-05-25 (17 days available)

---

## 1. Premise

A data-scientist workspace orchestrated by three specialist agents:

- **Research Agent** — surveys papers, blog posts, docs to summarize a problem space.
- **Data + Feature Engineering Agent** — pulls datasets, profiles them, builds features.
- **Modelling Agent** — selects models, runs hyperparameter tuning, reports metrics.

These agents are useful precisely because they have tools (web fetch, file/dataset access, code execution, model registries). That same surface is what attackers target. We use Dynatrace as the workspace's **immune system**: it observes every agent action, Davis AI flags anomalies, and a **Sentinel Agent** queries Dynatrace over MCP before risky actions — closing the loop from detection to response.

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

### Local toolchain
- Python 3.11+, `uv` or `poetry`
- `gcloud` CLI authenticated
- Node.js 20+ (for any MCP tooling)
- Docker (for reproducible workspace + optional sandboxing)

### Python packages (initial)
- **Agents:** `google-adk` (Agent Development Kit) **or** `langgraph` — pick one in Day 1
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
- A polished UI — a CLI + a single Dynatrace dashboard is enough
- Production-grade sandboxing of agent tool execution

---

## 5. Topics to study (front-load Days 1–3)

### Must-read / must-watch
1. **Dynatrace AI Observability** — how OTel traces from LLM apps surface in Dynatrace; the "AI & LLM Observability" docs.
2. **Dynatrace MCP server** — available tools, auth model, response shapes. Spend an hour calling each tool from a notebook before designing the Sentinel Agent.
3. **Davis AI problem detection** — how baselines form, how to seed custom events, how problem IDs map to entities.
4. **Google ADK (Agent Development Kit)** quickstart + multi-agent example. Compare against LangGraph if ADK feels heavy.
5. **OpenLLMetry / Traceloop** — drops in OTel instrumentation for LLM + tool calls with one line; saves a day of work.

### Threat-modelling references
- OWASP Top 10 for LLM Applications (2025) — especially LLM01 (prompt injection) and LLM03 (training data poisoning)
- MITRE ATLAS — tactics for ML systems
- Simon Willison's writeups on indirect prompt injection (concrete payload examples)

### Decisions to lock by end of Day 2
- ADK vs LangGraph
- Gemini model tier (Flash for cost during dev, Pro for demo)
- One LLM trace exporter (OpenLLMetry vs hand-rolled)
- Where the Sentinel Agent runs (in-process supervisor vs separate process)

---

## 6. Day-by-day breakdown

17 days, treated as **3 phases**: Foundation (1–6), Attack & Defense (7–12), Polish & Submit (13–17). Each day lists *outcome* — what exists at end of day — not hours.

### Phase 1 — Foundation (Days 1–6)

| Day | Date | Outcome |
|-----|------|---------|
| 1 | Mon May 25 | Repo scaffolded; ADK vs LangGraph chosen; `uv` env; Gemini "hello world" runs; Dynatrace OTLP token validated by sending one manual span. |
| 2 | Tue May 26 | Research Agent v0 — single agent, web fetch tool, returns a summary. Spans appear in Dynatrace. OpenLLMetry wired. |
| 3 | Wed May 27 | Feature Eng. Agent v0 + Modelling Agent v0 (skeletons). Orchestrator routes a request across all three. End-to-end trace visible in Dynatrace. |
| 4 | Thu May 28 | Dynatrace MCP client wired. Sentinel Agent v0 can call `list_problems`, `execute_dql` and print results. |
| 5 | Fri May 29 | Sentinel Agent integrated as pre-flight check — every tool call routed through it. Default policy: ALLOW. |
| 6 | Sat May 30 | **Milestone M1: Happy path works end-to-end and is fully observable.** A user request flows through 3 agents, Sentinel pre-checks each tool call, full trace visible in Dynatrace. No attacks yet. |

### Phase 2 — Attack & Defense (Days 7–12)

| Day | Date | Outcome |
|-----|------|---------|
| 7 | Sun May 31 | **A1 attack staged** — a local "malicious" webpage with embedded prompt injection; Research Agent visibly compromised (tries to call exfil tool). |
| 8 | Mon Jun 1 | A1 detection — emit a custom Dynatrace event when LLM input matches injection heuristics; Davis AI raises a problem. Verify problem appears via MCP. |
| 9 | Tue Jun 2 | A1 defense — Sentinel queries problems pre-flight, returns HALT, orchestrator quarantines the agent. End-to-end attack→detection→halt demo works. |
| 10 | Wed Jun 3 | **A2 attack staged** — poisoned CSV with label flips; Feature Eng. Agent ingests it; downstream model accuracy drops. |
| 11 | Thu Jun 4 | A2 detection + defense — emit dataset-stats metrics; Davis AI flags drift; Sentinel halts modelling step. |
| 12 | Fri Jun 5 | **Milestone M2: Both attack scenarios run end-to-end with detection and response.** Lock the demo script. |

### Phase 3 — Polish & Submit (Days 13–17)

| Day | Date | Outcome |
|-----|------|---------|
| 13 | Sat Jun 6 | Dynatrace dashboard built: workspace overview, agent activity, problem timeline. One-click "show the demo" view. |
| 14 | Sun Jun 7 | Demo script rehearsed; CLI UX cleaned up; README v1 written. |
| 15 | Mon Jun 8 | **Milestone M3: Demo video recorded** (3 min, both attacks, narrated). Re-record if rough. |
| 16 | Tue Jun 9 | Buffer day — fix anything embarrassing; tighten README; architecture diagram exported as image. |
| 17 | Wed Jun 10 | Final submission package: repo, video, devpost write-up, architecture diagram. **Submit at least 24h before deadline.** |
| — | Thu Jun 11 | Hard deadline. Do not touch the repo today. |

### Milestones summary

- **M1 (Sat May 30):** observable happy path
- **M2 (Fri Jun 5):** both attacks demoed end-to-end
- **M3 (Mon Jun 8):** demo video in the can
- **Submission:** Wed Jun 10 (one day buffer before the Jun 11 deadline)

If M1 slips past May 31, drop A2 and demo A1 only. If M2 slips past June 7, skip the dashboard polish. **Do not compromise on M3** — a hackathon submission without a working video underperforms a working video with rougher code.

---

## 7. Risks & mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Dynatrace MCP tools don't expose what we need (e.g., no per-entity problem feed) | Medium | Day 1 spike: call every MCP tool, document responses. Fall back to direct Dynatrace API if MCP is thin. |
| ADK's multi-agent orchestration has rough edges | Medium | Have LangGraph as a backup; both can wrap the same tools. |
| Davis AI doesn't auto-detect our staged anomalies in time for demo | High | Don't rely on auto-detection alone — emit explicit custom events; Davis correlates them into problems quickly. |
| Demo flakes live (network, rate limits) | High | Record the video against a stable replay; never demo live for the submission. |
| Scope creep into "real" sandboxing or auth | High | This plan explicitly excludes them; revisit only post-M2. |

---

## 8. Full threat list (for the writeup, not the demo)

For completeness in the submission narrative — we'll mention these as future work:

1. **Indirect prompt injection** (A1, demoed)
2. **Data poisoning** (A2, demoed)
3. **Tool / MCP abuse** — agent tricked into calling destructive tools
4. **Model supply-chain poisoning** — malicious pre-trained model from a registry
5. **Resource abuse / cryptojacking** — compromised agent spawns miners during "tuning"
6. **Secret exfiltration** — agent reads env vars / credentials and sends them out
7. **Recursive agent loops** — DoS via runaway agent-to-agent calls

---

## 9. Open questions to resolve in Day 1

- ADK or LangGraph? (Bias: ADK, since it's the hackathon partner stack.)
- Where does the Sentinel Agent's policy live — code, or a Dynatrace-managed config?
- For the demo, do we replay a recorded trace or run live? (Bias: live for M2, recorded for the video.)
- Single-machine demo or split across a Cloud Run service + local CLI?
