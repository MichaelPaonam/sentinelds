# AI Security Threat Modelling — SentinelDS

This document is the threat-modelling reference for SentinelDS. It frames the agentic data-science workspace using two complementary lenses:

- **SANS AI Security Maturity Model (AISMM)** — *what* a mature AI security program looks like, by pillar and stage
- **RAI-AgentSec** — *how* concrete agent-shaped controls are evaluated and operationalized

The hackathon demo is deliberately narrow (two attacks, see [`agents-exploit-scenarios.md`](agents-exploit-scenarios.md)). This doc explains the broader frame those two scenarios sit inside, so the submission narrative — "Dynatrace as the workspace's immune system" — is grounded in industry-recognized models rather than ad-hoc invention.

> **Sources:**
> - SANS AI Security Maturity Model™ (Chris Cochran, SANS Institute)
> - RAI-AgentSec — Responsible AI security/compliance toolkit for agent projects
> - `GEMINI.md` section 2 (architecture), section 4 (threat walkthroughs)

---

## 1. The Three Pillars Applied to SentinelDS

The AISMM organizes AI security around three pillars. SentinelDS's design touches all three, but the hackathon submission emphasizes **Protect** with a strong assist from **Utilize** (Davis AI doing detection work), and points at **Govern** as future work.

| Pillar | AISMM core question | How SentinelDS answers it |
|--------|--------------------|---------------------------|
| **Protect** | How are we securing AI implementations against adversarial attacks, data poisoning, prompt injection, model theft? | Every agent tool call is wrapped in an OTel span and gated by the Sentinel Agent's pre-flight check (ALLOW/WARN/HALT). The two demoed attacks (A1 prompt injection, A2 data poisoning) are blocked end-to-end. |
| **Utilize** | How are we using AI to detect threats and automate response? | Dynatrace Davis AI auto-baselines workspace telemetry and raises problems on anomalous behavior (unseen egress hosts, dataset stat drift, injection signatures). Sentinel queries Davis over MCP rather than re-implementing detection. |
| **Govern** | How are we managing AI-specific risks and ensuring responsible use? | Out of hackathon scope. The submission write-up acknowledges this gap and lists it as future work alongside the five non-demoed threats from section 5 below. |

The pillars are not independent. Without **Govern**, **Utilize** becomes uncontrolled experimentation and **Protect** lacks policy authority. SentinelDS's Sentinel-Agent decisions (HALT vs WARN vs ALLOW) are policy enforcement; in a real deployment that policy would live under a Govern function (AI Governance Council, documented agent owners, NHI lifecycle). The hackathon demo collapses this into hardcoded rules — sufficient to show the mechanism, insufficient as a production posture.

---

## 2. Where SentinelDS Sits on the AISMM Stages

The AISMM maturity stages are:

| Stage | Posture |
|-------|---------|
| 1 — Unaware | No formal approach; unmanaged AI |
| 2 — Reactive | Basic policies; tools blocked or ungoverned |
| 3 — Defined | Formal governance; controlled deployment; security use cases emerging |
| 4 — Managed | AI embedded in security ops; secured by design; quantitatively managed |
| 5 — Optimizing | AI-native; autonomous capabilities; self-improving defenses |

**SentinelDS demonstrates Stage 3 → Stage 4 capabilities for the workspace it observes.** Specifically:

### Stage 3 indicators present in the demo
- **Complete inventory of AI components** — three named agents (Research, Feature Eng., Modelling) with a Sentinel supervisor, all visible as distinct entities in Dynatrace
- **Structured logging with trace IDs across agent steps and tool calls** (Stage 3 Govern indicator) — this is exactly what the OTel instrumentation layer produces
- **Prompt injection and instruction manipulation defenses** — A1 detection + Sentinel HALT
- **Input validation on ingested data** — A2 dataset-stats detection
- **Controls mapped to MITRE ATLAS™** — A1 maps to ATLAS *Indirect Prompt Injection*; A2 maps to ATLAS *Poison Training Data*
- **Documented human owner for each agent** — implied by the demo narrative; the data-science team owns the workspace

### Stage 4 indicators partially present
- **Execution guardrails with real-time monitoring for agent API calls** — the Sentinel pre-flight check is a guardrail; "real-time" is honest because Davis AI baselining is near-real-time
- **Confused Deputy defenses** — A1 is the canonical Confused Deputy attack (the agent's legitimate web-fetch credentials are weaponized by attacker-controlled content). Sentinel's HALT decision is the defense.
- **Controls for cascading failures in multi-agent systems** — partial; quarantining the compromised agent stops propagation to downstream agents
- **Real-time prompt injection detection** — partial; the demo emits explicit custom events rather than relying on Davis baseline alone

### What's not Stage 4 in the demo
- No quantitative risk methodology (FAIR, ALE)
- No MLSecOps pipeline (model provenance, training-data validation as production controls)
- No automated NHI lifecycle for the agents
- No bias/fairness monitoring

This is acceptable: hackathon judging rewards a tight story over a survey, and a hackathon submission cannot honestly claim board-level risk reporting.

> **Honest framing for the demo narrative:** "SentinelDS gives a Stage 1 / 2 data-science team the *observable plumbing and reflexes* of a Stage 3 / 4 program — without forcing them to build the governance overhead first."

---

## 3. Critical Strategic Drivers

The AISMM calls out four cross-cutting concerns. SentinelDS's relationship to each:

### Agentic AI and Identity (Principle of Least Agency)
- The companion "as-is" workflow (manual notebooks) is the AISMM "less autonomous architecture" baseline. SentinelDS is the agentic upgrade. The narrative must justify *why* agency is needed (parallelism, scale of literature/data) rather than treating it as the default.
- **NHI** — each agent should have a distinct service identity. In the demo this is approximated by labeling spans with `agent.name`; production would require per-agent GCP service accounts and per-agent Dynatrace API tokens.

### Data Maturity
- The Feature Engineering Agent ingests CSVs. AISMM's Stage 2 prerequisite — *data classification* — is what would tell us a poisoned dataset matters. The A2 attack works precisely because the workspace has no classification on ingested data; Sentinel + Davis is a compensating control.

### Incident Ownership
- A1 (prompt injection / exfil) is unambiguously a **Security Incident** — Security Team owns response.
- A2 (data poisoning) sits on the **Security ↔ Safety/Reliability boundary** — Security owns the attack vector, but Reliability owns the model-quality consequence. The demo handles both by halting the modelling step before bad data reaches training.

### Workforce AI Literacy
- Out of scope for the demo, but worth flagging: the data-science team using SentinelDS does not need to know prompt-injection theory. The platform absorbs that responsibility.

---

## 4. RAI-AgentSec Mapping — Concrete Controls for SentinelDS

RAI-AgentSec defines six agent-shaped checks that map directly onto SentinelDS architecture decisions. Two are central to the demo; the rest are deferred but should be acknowledged.

| RAI-AgentSec check | What it validates | SentinelDS relevance |
|--------------------|-------------------|----------------------|
| `rai-trace-compliance-checks` | OpenTelemetry instrumentation level (L0–L3) | **Central.** SentinelDS targets the equivalent of L2/L3 — auto-instrument plus custom span attributes (`tool.name`, `tool.args.hash`, `dataset.uri`, `egress.host`). Without this, Davis AI has nothing to baseline. |
| `rai-hitl-security-checks` | Human-in-the-loop is implemented, deterministic, default-reject, non-bypassable | **Central, reframed.** The Sentinel Agent's HALT decision is a *machine-in-the-loop* analogue: deterministic (rule-based, not LLM-decided), default-reject on uncertainty, non-bypassable (every risky tool call routes through it). HITL proper is future work for high-impact actions. |
| `rai-mcp-hub-compliance-checks` | MCP usage goes through a managed hub, not direct connections | **Tangential.** SentinelDS uses Dynatrace MCP directly — appropriate for a hackathon, but a production deployment environment would proxy through a hub with auth/audit. |
| `rai-audit-log-compliance-checks` | Audit log coverage across event types | **Future work.** OTel traces give us *observability*; audit logs give us *non-repudiation*. The demo records traces; a production version would also emit `SecurityEvent` / `DataModificationEvent` / `ConfigurationChangeEvent` to a tamper-evident log. |
| `rai-pre-push-checks` | Pre-push hygiene (`.gitignore`, secrets, untracked files) | **Hygiene, not threat-model.** Already covered by `.env.example` + `.gitignore` discipline. |
| `rai-aeval-testcase-generator` | Generates adversarial test cases (goal hijacking, jailbreak, bias, system-prompt extraction) | **Adjacent.** The SentinelDS "attack staging" scripts (A1 malicious page, A2 poisoned CSV) are the same idea, scoped to the two demoed threats rather than a full red-team panel. |

> **Defense in depth (per RAI-AgentSec disclaimer):** the agent-shaped controls above are not a replacement for SAST, DAST, SCA, secret scanners, container scanning, IAM reviews, etc. SentinelDS's contribution is the *agent-shaped* layer; it presumes the conventional layer is also in place.

---

## 5. The Threat Catalog — Demoed vs. Future

SentinelDS demos two threats end-to-end. Five additional threats are listed below as future work. Mapping each to AISMM pillars and ATLAS techniques:

| # | Threat | Target agent | Pillar | ATLAS technique (closest) | Demo? |
|---|--------|--------------|--------|---------------------------|-------|
| **A1** | Indirect prompt injection (malicious instructions in fetched webpage) | Research Agent | Protect | AML.T0051 — LLM Prompt Injection: Indirect | **Yes** |
| **A2** | Data poisoning (label-flipped + trigger pattern in CSV) | Feature Eng. Agent | Protect | AML.T0020 — Poison Training Data | **Yes** |
| 3 | Tool / MCP abuse — agent tricked into calling destructive tools | Any | Protect | AML.T0053 — LLM Plugin Compromise | Future |
| 4 | Model supply-chain poisoning — malicious pre-trained model from registry | Modelling Agent | Protect | AML.T0010 — ML Supply Chain Compromise | Future |
| 5 | Resource abuse / cryptojacking via "tuning" job | Modelling Agent | Protect | AML.T0034 — Cost Harvesting | Future |
| 6 | Secret exfiltration (env vars, credentials) | Any | Protect | AML.T0024.001 — Infer Training Data Membership / data exfil | Future |
| 7 | Recursive agent loops — DoS via runaway agent-to-agent calls | Orchestrator | Protect | AML.T0029 — Denial of ML Service | Future |

**Why these two for the demo** (per `GEMINI.md` section 4):
- A1 is the #1 real-world agent threat in 2026 and is visually compelling
- A2 is the classic ML attack and exercises a different defense path (statistical drift, not behavioral)
- Together they show *behavioral* detection (A1) and *data-shaped* detection (A2), proving the architecture generalizes

---

## 6. Defense Loop — How SentinelDS Closes the Loop

Every demoed attack follows the same four-phase defense loop. This is the architectural claim of the project; it should be the thing the demo video makes obvious.

```
  ┌────────────┐    ┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
  │ 1. EMIT    │───▶│ 2. DETECT    │───▶│ 3. DECIDE       │───▶│ 4. ENFORCE   │
  │            │    │              │    │                 │    │              │
  │ OTel spans │    │ Davis AI +   │    │ Sentinel Agent  │    │ Orchestrator │
  │ + custom   │    │ custom event │    │ queries Dyna-   │    │ skips tool   │
  │ events     │    │ correlation  │    │ trace MCP       │    │ call; quar-  │
  │ from every │    │ raises a     │    │ pre-flight,     │    │ antines the  │
  │ tool call  │    │ Problem on   │    │ returns ALLOW/  │    │ compromised  │
  │            │    │ workspace    │    │ WARN/HALT       │    │ agent        │
  └────────────┘    └──────────────┘    └─────────────────┘    └──────────────┘
       │                  │                    │                      │
   Observability       Detection           Authorization          Response
   (Pillar:            (Pillar:            (Pillar:               (Pillar:
    Protect)            Utilize)            Protect+Govern)        Protect)
```

**Mapping to AISMM stage indicators:**
- Phase 1 (Emit) is the Stage 3 *"structured logging with trace IDs across agent steps and tool calls"* indicator
- Phase 2 (Detect) is the Stage 3 *"AI-powered threat detection tuned to environment"* indicator, leaning on Davis AI as the tuned detector
- Phase 3 (Decide) is the Stage 4 *"execution guardrails with real-time monitoring for AI agent API calls"* indicator
- Phase 4 (Enforce) is the Stage 4 *"controls for cascading failures in multi-agent systems"* indicator

The Sentinel Agent is the novel piece. Davis AI does detection; MCP is the integration mechanism; the *decision* and *enforcement* steps are what SentinelDS contributes.

---

## 7. Trust Boundaries

The threat model assumes the following trust boundaries. Crossing one is what makes a payload dangerous; SentinelDS instruments every crossing.

| Boundary | Trusted side | Untrusted side | Crossing event |
|----------|--------------|----------------|----------------|
| External web ↔ Research Agent | Agent runtime | Fetched page content | `tool.web_fetch` span |
| Filesystem ↔ Feature Eng. Agent | Agent runtime | Ingested CSV bytes | `tool.csv_read` span |
| Model registry ↔ Modelling Agent | Agent runtime | Downloaded model artifact | `tool.model_load` span (future-work threat #4) |
| Agent ↔ Agent | Each agent's own context | Other agent's output | A2A handoff span |
| Workspace ↔ External egress | Agent runtime | Outbound network | `egress.host` attribute on any tool span |

A core AISMM principle (Confused Deputy, Stage 4 Protect indicator): **untrusted input must not be allowed to issue privileged actions through a trusted agent.** A1 is exactly this: untrusted webpage content tries to ride the Research Agent's legitimate egress permission to exfiltrate. The Sentinel pre-flight is the Confused Deputy defense.

---

## 8. What This Document Is *Not*

- **Not a checklist for production deployment.** A real deployment needs governance artifacts (AI Governance Council, NHI lifecycle, audit logs, board reporting) that the hackathon demo does not produce.
- **Not a comprehensive ATLAS coverage map.** Two ATLAS techniques are demoed, five more are named as future work. Real Stage 4 ATLAS coverage is broader.
- **Not a replacement for conventional AppSec.** Per the RAI-AgentSec disclaimer: SAST/DAST/SCA/secret-scanning still apply. SentinelDS adds the agent-shaped layer on top.
- **Not the demo script.** The two attack scenarios with step-by-step traces are in [`agents-exploit-scenarios.md`](agents-exploit-scenarios.md).

---

## 9. Quick Reference

**One-line pitch:** *Dynatrace as the AI agent immune system: every action is observed, anomalies become Problems, and a Sentinel Agent halts the next risky tool call before damage spreads.*

**Maturity claim:** Stage 3 indicators fully demonstrated (inventory, structured agent tracing, ATLAS-mapped controls). Stage 4 indicators partially demonstrated (execution guardrails, Confused Deputy defense, cascading-failure containment).

**Pillar focus:** Protect (primary), Utilize (Davis AI does the detection work), Govern (acknowledged as future work).

**Two demoed threats:** A1 indirect prompt injection (Research Agent); A2 data poisoning (Feature Eng. Agent). Full walk-through in [`agents-exploit-scenarios.md`](agents-exploit-scenarios.md).
