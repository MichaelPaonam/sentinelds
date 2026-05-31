# Dynatrace MCP options for SentinelDS — comparison & decision

This doc compares five overlapping Dynatrace offerings that all involve "MCP" or "agentic" framing, picks the one we use for the [Sentinel Agent](ai-security-threat-modelling.md) pre-flight gate, and records the fallback ladder.

The decision belongs to issue [#23 — Dynatrace MCP client wired to Sentinel Agent v0](https://github.com/MichaelPaonam/sentinelds/issues/23) (Day-1 spike output, parent #17). Cross-reference: [`ai-security-threat-modelling.md` §6](ai-security-threat-modelling.md) (Phase 3 DECIDE).

> **Sources adversarially verified** against the upstream `dynatrace-oss/dynatrace-mcp` repo, the Dynatrace Hub, and Dynatrace docs in June 2026. Where a claim could not be confirmed end-to-end, it is tagged **⚠ unverified** inline.

---

## Quick comparison table

| Option | What it is | How invoked | Auth | Sentinel-fit |
|---|---|---|---|---|
| Dynatrace Local MCP Server (`@dynatrace-oss/dynatrace-mcp-server`) | Self-hosted Node MCP server exposing ~17 Dynatrace tools (problems, DQL, entities, Davis, notifications) | `npx -y @dynatrace-oss/dynatrace-mcp-server@latest` (stdio) or `--http --port 3000`; Python `mcp` SDK as client | Platform Token / OAuth client credentials / browser OAuth (+ optional `DT_SSO_URL`) | **High — recommended** |
| Dynatrace Remote MCP Server (Hub) | Hosted equivalent of the local server, GA on the Dynatrace Hub | `streamablehttp_client(<hub_url>)` from Python `mcp` SDK | Same Dynatrace platform OAuth / Platform Token | **High** (forward path; docs thinner) |
| Dynatrace AI Observability app | Hub-installed Grail app that ingests OTel GenAI traces (incl. MCP + ADK) | Not invoked directly — receives OTLP from Traceloop / native OTel exporter | OTLP `Authorization: Api-Token` with `openTelemetryTrace.ingest` scope | High **as data source for DQL**, not as the gate itself |
| Dynatrace Workflows / AutomationEngine | Event-driven async automation in the Dynatrace tenant | Triggered by events / schedule; no documented sync run-and-wait API | Platform OAuth, `automation:workflows:read\|write\|run` | **Low** — async, not a sub-second pre-flight gate |
| (Reference: `dynatrace-oss/dynatrace-mcp` repo) | Same artefact as the Local MCP Server above; listed because two research entries describe it | See Local MCP row | See Local MCP row | **High** (duplicate) |

---

## Per-option detail

### 1. Dynatrace Local MCP Server (`@dynatrace-oss/dynatrace-mcp-server`)

- **Purpose.** Bridge MCP-aware clients to a Dynatrace SaaS tenant. For SentinelDS this is the data source the Sentinel Agent calls before risky tool invocations to compute ALLOW / WARN / HALT.
- **Invocation.** Default stdio: `npx -y @dynatrace-oss/dynatrace-mcp-server@latest` (Node.js ≥ 22.10). HTTP transport: same binary with `--http --port 3000 --host 127.0.0.1`. From Python use the official `mcp` SDK with `StdioServerParameters` + `stdio_client`, or `streamablehttp_client` for the HTTP transport. A Dockerfile is in the repo; a pre-published Docker image was claimed in research but **⚠ unverified**.
- **Auth.** Three modes via env vars: (1) browser OAuth Authorization Code Flow (interactive, dev only), (2) Platform Token (`DT_PLATFORM_TOKEN`, headless-friendly), (3) OAuth client credentials (`OAUTH_CLIENT_ID` + `OAUTH_CLIENT_SECRET`, service-to-service). Optional `DT_SSO_URL` SSO override. Minimum scopes for the Sentinel pre-flight: `app-engine:apps:run` plus the relevant `storage:*:read` scopes (`storage:events:read`, `storage:entities:read`, etc.). `storage:events:write` only if Sentinel writes its own custom events back.
- **Tools.** `list_problems`, `list_vulnerabilities`, `list_exceptions`, `get_kubernetes_events`, `execute_dql`, `verify_dql`, `generate_dql_from_natural_language`, `explain_dql_in_natural_language`, `find_entity_by_name`, `chat_with_davis_copilot`, `list_davis_analyzers`, `execute_davis_analyzer`, `create_workflow_for_notification`, `send_slack_message`, `send_email`, `send_event` (human-approval-gated as of v1.8.6), `create_dynatrace_notebook`. A `reset_grail_budget` tool was claimed in research but is **⚠ unverified** — Grail budget is governed by the `DT_GRAIL_QUERY_BUDGET_GB` env var (default 1000), not an exposed tool.
- **Pros.** Tool surface aligns 1:1 with Sentinel pre-flight needs (`list_problems` + `execute_dql` + `find_entity_by_name`). Multiple auth modes including headless. Stdio co-locates with the Python agent — no extra network hop, no inbound port. Built-in Grail GB budget guard. Telemetry opt-out via `DT_MCP_DISABLE_TELEMETRY=true`. Fine-grained scopes let Sentinel be locked read-only.
- **Cons.** Repo is explicitly in **Maintenance Mode** (tracked in upstream issue #496) — Dynatrace steers new users to the Remote MCP Server. Node 22.10+ adds a non-Python runtime dep. Tool I/O schemas are not exhaustively documented — confirm by Day-1 spike. Default browser OAuth is interactive; headless setup needs deliberate config. `send_event` got a human-approval gate in v1.8.6 — auto-pushing Sentinel verdicts back into Dynatrace via this tool is no longer a clean path. Davis Copilot tools require a tenant SKU that hackathon trials may not have.
- **GA status.** Open-source, MIT-licensed, latest **v1.8.6 (2026-05-29)**. Maintenance mode per repo README (announced in v1.8.4). Not covered by Dynatrace commercial support; community support via GitHub Issues only.
- **Sources.**
  - [github.com/dynatrace-oss/dynatrace-mcp](https://github.com/dynatrace-oss/dynatrace-mcp)
  - [github.com/dynatrace-oss/dynatrace-mcp/releases](https://github.com/dynatrace-oss/dynatrace-mcp/releases)
  - [github.com/dynatrace-oss/dynatrace-mcp/issues/496](https://github.com/dynatrace-oss/dynatrace-mcp/issues/496)
  - [dynatrace.com/hub/detail/dynatrace-mcp-server](https://www.dynatrace.com/hub/detail/dynatrace-mcp-server/)
  - [github.com/modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)

### 2. Dynatrace Remote MCP Server (Dynatrace Hub)

- **Purpose.** Hosted Dynatrace MCP Server, advertised on the Dynatrace Hub as the forward path. Same conceptual surface as the local server but with no local Node process to babysit.
- **Invocation.** Connect with the Python `mcp` SDK's `streamablehttp_client(<hub_url>)`; URL is surfaced in the tenant's Hub entry.
- **Auth.** Same Dynatrace platform OAuth / Platform Token model.
- **Tools.** Same canonical Dynatrace tool set (treat as superset of local; exact parity should be confirmed during the spike — public docs are still thin).
- **Pros.** No Node dependency in the SentinelDS process tree. GA on the Hub. Forward-supported path.
- **Cons.** Public schema docs are thinner than the open-source repo's README, so the Day-1 spike is more important. Network round-trip is non-zero — keep DQL timeframes tight to stay under 1 s pre-flight latency.
- **GA status.** Confirmed GA on the Dynatrace Hub page; Local MCP is positioned as a "playground or to customize modules."
- **Sources.**
  - [dynatrace.com/hub/detail/dynatrace-mcp-server](https://www.dynatrace.com/hub/detail/dynatrace-mcp-server/)
  - [github.com/dynatrace-oss/dynatrace-mcp/blob/main/docs/remote-mcp-migration.md](https://github.com/dynatrace-oss/dynatrace-mcp/blob/main/docs/remote-mcp-migration.md)

### 3. Dynatrace AI Observability app (a.k.a. "MCP AI Agent Monitoring")

- **Purpose.** Hub-installed Grail app that ingests OTel GenAI traces and renders an agent-aware view with tool-invocation tracking — explicitly including MCP tools and Google ADK.
- **Invocation.** Not directly callable from the Sentinel pre-flight. It is the **receiving end** of the OTel pipeline (Traceloop / native OTel exporter), and its data lives in Grail — so the Sentinel Agent reaches it indirectly via `execute_dql` against the spans/events it produces.
- **Auth.** Standard Dynatrace OTLP ingest: tenant OTLP endpoint + `Authorization: Api-Token` with `openTelemetryTrace.ingest` scope.
- **Tools / capabilities.** Agent execution path view, MCP & ADK tool-call surfacing, prompt/response capture, token/cost/latency/error metrics, drift signals, OTel GenAI semconv attributes.
- **Pros.** Officially names MCP and ADK as supported. Pure OTel ingest — no Dynatrace-specific SDK in the agent. Same Grail backs both this app and the MCP server's `list_problems` / `execute_dql`, so Sentinel queries can join on the agent entity it materialises. Captures prompt/response payloads, useful for the A1 (indirect prompt injection) post-mortem slide.
- **Cons.** Not a synchronous gate. Davis-on-agent-spans is **not** documented as a named feature — don't promise "Davis caught the prompt injection." Exact attribute schema and which Davis detectors fire on agent spans are thin in public docs as of June 2026. **⚠ Treat the agent-specific surfaces as recently-shipped, not formally GA.**
- **GA status.** Hub app v2.2.11 is shipping; Apr–May 2026 Dynatrace blog posts describe production usage, but no doc reviewed labels the agent-specific surfaces "GA" verbatim.
- **Sources.**
  - [docs.dynatrace.com/.../dynatrace-for-ai-observability](https://docs.dynatrace.com/docs/analyze-explore-automate/dynatrace-for-ai-observability)
  - [dynatrace.com/hub/detail/ai-and-llm-observability](https://www.dynatrace.com/hub/detail/ai-and-llm-observability/)
  - [dynatrace.com/news/blog/dynatrace-expands-ai-coding-agent-monitoring](https://www.dynatrace.com/news/blog/dynatrace-expands-ai-coding-agent-monitoring/)

### 4. Dynatrace Workflows (AutomationEngine) — "Agentic Workflows"

- **Purpose.** Event-driven automation inside the Dynatrace tenant. Reacts to Davis problems / security events / custom biz-events; runs connectors and JS tasks.
- **Invocation.** Event trigger (POST a biz-event), schedule trigger, or manual run from the UI. The MCP Server can `create_workflow_for_notification` and `send_event` to fire triggers — but **there is no documented synchronous "run this workflow now and return the verdict" tool**.
- **Auth.** Platform OAuth / Platform Token with `automation:workflows:read|write|run` (`admin` for full management).
- **Tools / capabilities.** Event/schedule/manual triggers, conditional logic, retries, loops, parallel branches, Slack/email/Jira/ServiceNow/cloud connectors, run-JavaScript step, full audit trail.
- **Pros.** Native to Dynatrace, no extra infra. First-class Davis-problem and security-problem triggers. Built-in audit trail. Good as the **post-HALT reaction layer** (page on-call, open ticket, freeze workspace).
- **Cons.** Async by design — not built to return ALLOW/WARN/HALT to a blocking caller in <1 s. No documented sync REST endpoint. Adds a second policy surface (Workflows DSL) on top of Sentinel's Python policy — risks scope creep against `PLAN.md` §4. "Agentic" framing in marketing refers to Dynatrace's own built-in agents, not a host for external Python agents.
- **GA status.** GA on the Dynatrace Platform (Grail/AppEngine generation). Not preview. Consumption-priced; workflow executions and any DQL inside them count against Grail budget.
- **Sources.**
  - [docs.dynatrace.com/docs/shortlink/workflows](https://docs.dynatrace.com/docs/shortlink/workflows)
  - [docs.dynatrace.com/docs/platform-modules/automations/workflows](https://docs.dynatrace.com/docs/platform-modules/automations/workflows)

### 5. "MCP Server Tools on Dynatrace" — the tool catalogue

This phrasing in the user's prompt refers to the *catalogue of tools the Dynatrace MCP server exposes*, not a separate product. It is fully covered by §1 above (the `tools_or_capabilities` list) and §2 (same set, hosted). Top-3 tools relevant to the Sentinel pre-flight:

1. `list_problems` — open Davis problems on the workspace entity. Direct hit on issue #23 acceptance criterion 1.
2. `execute_dql` — Grail query for custom Sentinel attack events / span filters. Direct hit on issue #23 acceptance criterion 2.
3. `find_entity_by_name` — resolve the workspace entity ID once at startup so the other two can be scoped.

`verify_dql` is a useful adjunct (lint a DQL string before sending it). `send_event` was useful pre-v1.8.6 for emitting Sentinel verdicts back into Dynatrace, but is now human-approval-gated; emit verdicts over OTel directly instead.

---

## Recommendation

**Build issue #23 against the Local Dynatrace MCP Server (`@dynatrace-oss/dynatrace-mcp-server`, pinned to a 1.8.x release), spawned over stdio from the Python Sentinel Agent using the [`mcp` PyPI package](https://github.com/modelcontextprotocol/python-sdk), authenticated with a `DT_PLATFORM_TOKEN` env var.**

- **Direct hit on the acceptance criteria.** The two MCP tools issue #23 names by hand — `list_problems` and `execute_dql` — are first-class on this server with those exact names, and `find_entity_by_name` resolves the workspace entity id once at startup. Auth via env-loaded Platform Token cleanly satisfies the "no hardcoded credentials" bullet.
- **Lowest-friction path to M1 / M2 on the Jun 11 deadline.** Stdio co-locates the server with the Python process — no inbound port, no extra Cloud Run service, sub-second round-trips fit a synchronous pre-flight gate. The Python `mcp` SDK already ships in the project's deps.
- **Drops the Remote MCP Server** as the *primary* target only because its public schema docs are thinner in June 2026 — but it is the migration target post-hackathon; keep the client behind a transport-abstraction so swapping `stdio_client` for `streamablehttp_client` is one file.
- **Drops Dynatrace AI Observability** as the gate. It stays in the architecture as the **OTel sink** so the demo dashboard tells the full agent story, and Sentinel's `execute_dql` queries can target spans/events it produces — but it is not synchronously callable.
- **Drops Workflows** from the pre-flight loop entirely (async, no sync run-and-wait). Keep one slide showing it as the **post-HALT reaction layer** (Sentinel HALT → workflow pages on-call), which is honest to `PLAN.md` §3 without inflating scope.

Caveats acknowledged honestly: the local repo is in maintenance mode, `send_event` is human-approval-gated as of v1.8.6 (so auto-emit Sentinel verdicts over OTel directly, not via `send_event`), and the Davis-on-agent-spans story is **⚠ unverified** as a named feature, so the demo narration says "Sentinel pre-flight queries Dynatrace for problems" rather than "Davis caught the prompt injection."

---

## Implementation sketch

Pin a recent 1.8.x version, spawn over stdio, auth via env-loaded `DT_PLATFORM_TOKEN`. The Sentinel Agent owns one long-lived `ClientSession` per workspace and reuses it for every pre-flight.

```python
# src/sentinel/dynatrace_mcp.py  (excerpt)
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass(frozen=True)
class DynatraceMCPConfig:
    environment: str
    platform_token: str
    server_version: str = "1.8.6"
    disable_telemetry: bool = True
    grail_budget_gb: int = 50

    @classmethod
    def from_env(cls) -> "DynatraceMCPConfig":
        return cls(
            environment=os.environ["DT_ENVIRONMENT"],
            platform_token=os.environ["DT_PLATFORM_TOKEN"],
        )


@asynccontextmanager
async def dynatrace_session(cfg: DynatraceMCPConfig):
    params = StdioServerParameters(
        command="npx",
        args=["-y", f"@dynatrace-oss/dynatrace-mcp-server@{cfg.server_version}"],
        env={
            "DT_ENVIRONMENT": cfg.environment,
            "DT_PLATFORM_TOKEN": cfg.platform_token,
            "DT_MCP_DISABLE_TELEMETRY": "true" if cfg.disable_telemetry else "false",
            "DT_GRAIL_QUERY_BUDGET_GB": str(cfg.grail_budget_gb),
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def list_open_problems(session: ClientSession, entity_id: str) -> list[dict[str, Any]]:
    result = await session.call_tool(
        "list_problems", {"entity": entity_id, "status": "OPEN"}
    )
    payload = json.loads(result.content[0].text)
    return payload.get("problems", [])


async def run_dql(session: ClientSession, query: str) -> list[dict[str, Any]]:
    result = await session.call_tool("execute_dql", {"query": query})
    payload = json.loads(result.content[0].text)
    return payload.get("records", [])
```

Live response shapes are pinned in [`dynatrace-mcp-notes.md`](dynatrace-mcp-notes.md) once the spike completes against a real tenant.

---

## Fallback ladder (per issue #23 Risk note)

All four tiers stay behind the same `list_open_problems` / `run_dql` Python signatures so the Sentinel gate code never changes:

1. **MCP transport swap** — re-point `ClientSession` at the **Remote Dynatrace MCP Server** via `mcp.client.streamable_http.streamablehttp_client(<hub_url>)`. Same tool names, same auth, no Node process.
2. **Direct REST API** — drop MCP entirely, hit `GET /platform/classic/environment-api/v2/problems` and `POST /platform/storage/query/v1/query:execute` with the same `DT_PLATFORM_TOKEN` as `Authorization: Api-Token`. Document the decision in `dynatrace-mcp-notes.md` before any defense logic builds on it.
3. **Grail unavailable** — degrade `run_dql` to return `[]`; Sentinel relies on `list_problems` plus an in-process counter of recently-emitted custom OTel attack events. Demo story unchanged.
4. **Last resort for the recorded video (M3 — never compromise M3)** — replay a fixture of `list_problems` / `execute_dql` responses captured during a successful live run. Sentinel logic and demo narration unchanged.

---

## Notes on the research process

This decision was made via a multi-agent research workflow that fanned out one research agent per option, ran an adversarial verifier against each finding, and then synthesised the table above. Two minor verifier corrections were rolled in: the recommended pin is **1.8.x** (not 0.12/0.13 as one finder suggested), and `reset_grail_budget` is not a confirmed tool — Grail budget is governed by the `DT_GRAIL_QUERY_BUDGET_GB` env var. One fetched page during research contained a prompt-injection payload (a fake "Plan mode" reminder embedded in HTML); it was correctly ignored as page content — itself a useful demonstration of the A1 attack class SentinelDS exists to defend against.
