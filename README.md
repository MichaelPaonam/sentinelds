# SentinelDS

An agentic data-science workspace defended by Dynatrace.

Submission for the [Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com) — partner: **Dynatrace** (via MCP). Deadline: **2026-06-11**.

## What it is

Three specialist agents — **Research**, **Feature Engineering**, **Modelling** — collaborate on data-science tasks. Each agent's actions (LLM calls, tool calls, dataset I/O) are instrumented as OpenTelemetry and shipped to Dynatrace. A **Sentinel Agent** queries Dynatrace over MCP before each risky tool call and decides ALLOW / WARN / HALT, using Davis AI's anomaly signals to spot compromise in real time.

## What we're demonstrating

Two attacks, end-to-end, with detection and response:

- **A1 — Indirect prompt injection**: a malicious webpage tells the Research Agent to exfiltrate data. Dynatrace flags the anomalous behavior; Sentinel halts the next call.
- **A2 — Data poisoning**: a crafted CSV with label flips reaches the Feature Engineering Agent. Dynatrace surfaces the data drift; Sentinel halts the modelling step.

Five other threats are catalogued in `PLAN.md` §8 as future work.

## Repo layout

- `PLAN.md` — full technical plan: threat model, architecture diagram, prerequisites, day-by-day schedule, milestones.
- *(code lands as the schedule progresses)*

## Setup & Development

We use `uv` for fast Python package and environment management. Ensure you have [uv](https://github.com/astral-sh/uv) installed.

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd sentinelds
   ```

2. **Create a virtual environment:**
   ```bash
   uv venv
   ```

3. **Activate the environment:**
   ```bash
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

4. **Sync dependencies:**
   ```bash
   uv sync
   ```

## Status

Pre-implementation. Plan locked, scaffolding starts on Day 1 of the schedule in `PLAN.md` §6.

## Milestones

- **M1 (May 30)** — observable happy path
- **M2 (Jun 5)** — both attacks demoed end-to-end
- **M3 (Jun 8)** — demo video recorded
- **Submission (Jun 10)**

## License

MIT — see [LICENSE](LICENSE).
