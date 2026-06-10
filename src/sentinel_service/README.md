# `sentinel_service` — Sentinel audit sidecar

A small FastAPI service deployed on Cloud Run as `sentinelds-sentinel`. It is the
fifth Cloud Run service alongside the Orchestrator, Research, Feature, and
Modeling agents and exists for **two reasons only**:

1. To give Sentinel its own **Smartscape entity** in Dynatrace
   (`service.name = "sentinelds-sentinel"`) so Davis AI correlates pre-flight
   telemetry against a single, named immune-system component instead of seeing
   it scattered across the four agent services.
2. To be a single, downstream **fan-out target** for audit pings from the
   in-process Sentinel gate that runs inside each agent. Each ping becomes one
   OTel span on the Sentinel service.

## What this service is NOT

- **Not a hot-path gate.** The `@sentinel_gate` decorator in
  [`src/tools/`](../tools/) and [`src/sentinel/preflight.py`](../sentinel/preflight.py)
  stays in-process and O(1). A sidecar outage cannot block any agent.
- **Not the source of policy.** Verdicts are still decided in
  `Sentinel.preflight()` and the inline detectors. The sidecar is downstream
  only — it observes, it does not decide.
- **Not running OneAgent.** Cloud Run does not expose host-kernel access, so
  OneAgent is unsupported; we use OTLP/HTTP via
  [`observability.init_tracing`](../observability/otel.py). Sentinel appears as
  a `SERVICE` entity in Smartscape, not a `HOST`.

## Architecture in one paragraph

The four agent services each carry the Sentinel library inline and run
`@sentinel_gate` decorators on risky tools. When a verdict is produced or a
local detector flips the compromise flag, the agent fires a fire-and-forget
POST to this sidecar via [`core.sentinel_audit.emit_audit`](../core/sentinel_audit.py)
— the env var `SENTINEL_AUDIT_URL` controls whether that fan-out happens. The
sidecar receives the JSON, wraps it in an OTel span named
`sentinel.audit:<event.type>`, and lets `init_tracing` ship it to Dynatrace.
A background heartbeat task ([`heartbeat.py`](heartbeat.py)) opens its own
remote Dynatrace MCP session every 60s, calls `query-problems`, and emits a
`sentinel.heartbeat` span — keeping the Sentinel entity "alive" in Smartscape
even when no agent is currently calling the gate.

## Files

| File | Role |
|---|---|
| [`main.py`](main.py) | FastAPI app + lifespan-managed heartbeat. Routes: `GET /health`, `POST /audit`. |
| [`heartbeat.py`](heartbeat.py) | `HeartbeatTask`: periodic Dynatrace MCP ping that emits `sentinel.heartbeat` spans. |
| [`Dockerfile`](Dockerfile) | Cloud Run image. Mirrors `src/a2a_agents/a2a_research/Dockerfile`. |
| [`../../deploy_sentinel_service.sh`](../../deploy_sentinel_service.sh) | Deploy script (Cloud Run, region `europe-west4`). |
| [`../../tests/test_sentinel_service.py`](../../tests/test_sentinel_service.py) | Endpoint contract tests. |

## HTTP contract

### `GET /health`

Cloud Run liveness probe. Returns `200 OK` with
`{"status": "ok", "service": "sentinelds-sentinel"}`.

### `POST /audit`

Receives an audit payload from an agent and re-emits it as an OTel span.

- **Always returns `202 Accepted`** on a parseable body. We never return 4xx/5xx
  on a malformed payload — the agent's `emit_audit` is fire-and-forget and we
  must not tempt it into retry/backoff logic. The gate has already decided by
  the time we see the payload.
- **Bad JSON bodies are accepted too**, with the parse error logged and tagged
  on a `sentinel.audit.invalid` span.
- **Schema is intentionally loose.** Agents and the sidecar may version-drift
  in the wild; unknown fields are forwarded as `audit.<key>` span attributes
  so new event shapes show up immediately without redeploying the sidecar.

Two payload shapes are produced today, both from the in-process Sentinel:

#### Pre-flight verdicts (from `Sentinel.preflight()`)

```json
{
  "event.type": "sentinel.preflight",
  "workspace": "WORKSPACE-1",
  "agent": "research_agent",
  "tool": "web_fetch",
  "rule_fired": "CLEAN",
  "decision": "ALLOW",
  "input_problems": []
}
```

Becomes one span: `sentinel.audit:sentinel.preflight` with each field
forwarded as `audit.<key>`.

#### Injection-candidate events (from `emit_injection_candidate`)

```json
{
  "event.type": "sentinelds.injection.candidate",
  "span.id": "abc123",
  "matched_categories": ["INSTRUCTION_OVERRIDE", "URL_WITH_POST_VERB"],
  "match_count": 2,
  "excerpt_hash": "deadbeef",
  "source_url": "http://attacker.example.com",
  "workspace_entity_id": "WORKSPACE-1"
}
```

Becomes one span: `sentinel.audit:sentinelds.injection.candidate`. List values
are joined with `", "` to satisfy OTel attribute typing.

## Heartbeat

`HeartbeatTask` runs as a `lifespan` background task:

- Fires once **at startup** (so the entity appears in Smartscape immediately)
- Then every `SENTINEL_HEARTBEAT_INTERVAL` seconds (default `60`, minimum `10`)
- Each tick opens one remote MCP session, calls
  [`list_open_problems`](../sentinel/dynatrace_mcp.py) on the workspace entity,
  emits one `sentinel.heartbeat` span, closes
- **Soft-fails**. Missing `DT_ENVIRONMENT` / `DT_PLATFORM_TOKEN`, transient
  network, or MCP server errors all become `mcp.reachable = false` and a single
  WARN log line. The audit endpoint keeps working regardless.

Each heartbeat span carries:

| Attribute | Notes |
|---|---|
| `workspace.entity_id` | From `DYNATRACE_WORKSPACE_ENTITY_ID`, default `WORKSPACE-1`. |
| `mcp.reachable` | `true` if the MCP session opened and the call returned. |
| `mcp.error` | Short error string when `mcp.reachable = false`. |
| `dynatrace.problems.active` | Count of ACTIVE problems on the workspace. |

## Configuration

All env vars are optional from the sidecar's point of view — missing values
degrade gracefully, they don't crash the service.

| Env var | Required for | Default |
|---|---|---|
| `PORT` | Cloud Run injects it | `8080` |
| `SENTINEL_HEARTBEAT_INTERVAL` | Heartbeat cadence in seconds | `60` |
| `DT_ENVIRONMENT` | Heartbeat MCP calls | unset → `mcp.reachable=false` |
| `DT_PLATFORM_TOKEN` | Heartbeat MCP calls | unset → `mcp.reachable=false` |
| `DYNATRACE_API_URL` | OTLP span export | unset → spans drop on the floor |
| `DYNATRACE_API_TOKEN` | OTLP span export | unset → spans drop on the floor |
| `DYNATRACE_WORKSPACE_ENTITY_ID` | Heartbeat workspace scope | `WORKSPACE-1` |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | OTel semantic-convention version | `gen_ai_latest_experimental` |

The Cloud Run secret bindings used by [`deploy_sentinel_service.sh`](../../deploy_sentinel_service.sh)
match the four agent services: `dynatrace-api-url`, `dynatrace-api-token`,
`dt-environment`, `dt-platform-token`.

## Deploy

From the repo root, with `gcloud` authenticated and `GOOGLE_CLOUD_PROJECT` and
`OTEL_SEMCONV_STABILITY_OPT_IN` exported:

```bash
bash deploy_sentinel_service.sh
```

The script copies `src/sentinel_service/Dockerfile` to the repo root (so the
`COPY pyproject.toml uv.lock ./` lines resolve), runs
`gcloud run deploy sentinelds-sentinel --source=.`, and removes the temporary
Dockerfile on exit. Region is hard-coded to `europe-west4` to match the other
services.

## Wiring agents to fan out to this service

After the sidecar is deployed, set `SENTINEL_AUDIT_URL` on each of the four
agent services (Orchestrator, Research, Feature, Modeling). The URL **must
include the `/audit` path** — the agent-side fan-out POSTs to the URL verbatim:

```bash
SENTINEL_AUDIT_URL="https://sentinelds-sentinel-<hash>.<region>.run.app/audit"
```

When unset, [`core.sentinel_audit.emit_audit`](../core/sentinel_audit.py) is a
no-op. When set, every gate verdict and every injection-candidate event fans
out to the sidecar — failure to reach it is logged and swallowed, so a sidecar
outage cannot break the gate.

## Testing locally

The sidecar runs identically locally and on Cloud Run. Three useful tests, in
order of coupling.

### 1. Health + audit smoke (curl against deployed URL)

Cheapest sanity check — proves the deployment accepts traffic and the OTel
pipeline is wired correctly. Replace the URL below with your deployed
`sentinelds-sentinel` service URL:

```bash
SIDECAR=https://sentinelds-sentinel-<hash>.europe-west4.run.app

# Liveness
curl -sS "$SIDECAR/health"

# Pre-flight verdict
curl -sS -X POST "$SIDECAR/audit" \
  -H "content-type: application/json" \
  -d '{
    "event.type": "sentinel.preflight",
    "workspace": "WORKSPACE-1",
    "agent": "research_agent",
    "tool": "web_fetch",
    "rule_fired": "LOCAL_TEST_FROM_LAPTOP",
    "decision": "ALLOW",
    "input_problems": []
  }'

# Injection candidate
curl -sS -X POST "$SIDECAR/audit" \
  -H "content-type: application/json" \
  -d '{
    "event.type": "sentinelds.injection.candidate",
    "span.id": "manual-curl-test",
    "matched_categories": ["INSTRUCTION_OVERRIDE", "URL_WITH_POST_VERB"],
    "match_count": 2,
    "excerpt_hash": "deadbeef",
    "source_url": "http://attacker.example.com",
    "workspace_entity_id": "WORKSPACE-1"
  }'
```

Expected: `200` for `/health`, `202` for both audits. Cold start adds a few
seconds to the first request.

Then in Dynatrace:

```dql
fetch spans, from: now() - 30m
| filter service.name == "sentinelds-sentinel"
| sort timestamp desc
| limit 50
```

You should see `sentinel.heartbeat` spans (since deploy) plus the two
`sentinel.audit:*` spans from the curls. The `audit.rule_fired ==
"LOCAL_TEST_FROM_LAPTOP"` and `audit.span.id == "manual-curl-test"` flags help
distinguish smoke traffic from real demo runs.

### 2. Agent → deployed sidecar fan-out (most valuable test before redeploy)

Run an agent locally and point it at the deployed sidecar. This exercises the
full fan-out path that step 4 will turn on for the Cloud Run agents.

```bash
export SENTINEL_AUDIT_URL="https://sentinelds-sentinel-<hash>.europe-west4.run.app/audit"

PYTHONPATH=src uv run python -m e2e.run_demo \
  --csv "$E2E_DEFAULT_CSV" \
  --paper-url "$E2E_PAPER_URL" \
  --target "$E2E_TARGET_COL"
```

Expected on the `sentinelds-sentinel` service in Dynatrace: one
`sentinel.audit:sentinel.preflight` span per gate fire, plus a
`sentinel.audit:sentinelds.injection.candidate` span when the staged attack
server fires the A1 payload.

### 3. Run the sidecar locally (offline iteration on the service itself)

When iterating on the sidecar code, run it on `localhost` and post to it
directly:

```bash
PYTHONPATH=src uv run python -m sentinel_service.main
# In another shell:
curl -sS http://localhost:8080/health
curl -sS -X POST http://localhost:8080/audit \
  -H "content-type: application/json" \
  -d '{"event.type": "sentinel.preflight", "tool": "web_fetch", "decision": "ALLOW"}'
```

Without `DT_ENVIRONMENT` / `DT_PLATFORM_TOKEN`, the heartbeat will log a warning
each tick (`mcp.reachable=false`) — the audit endpoint still serves.

### 4. Unit tests

```bash
uv run python -m pytest tests/test_sentinel_service.py tests/test_sentinel_audit.py -v
```

These cover both the sidecar contract (health, preflight payload,
injection-candidate payload, unknown event type, invalid JSON) and the
agent-side fan-out client (`emit_audit` no-op when unset, POST when set,
swallowing of HTTP and transport errors).

## Common gotchas

- **`SENTINEL_AUDIT_URL` without `/audit`.** The agent posts to the URL
  verbatim. If you set it to the service base, every fan-out hits `/` and
  the sidecar returns `404 Not Found`. The agent logs a warning and continues
  — no span is produced. Always include the `/audit` suffix.
- **Cold-start latency on the first request.** Cloud Run scales `sentinelds-sentinel`
  to zero by default. The first POST after idle takes a few seconds; the
  agent-side timeout is 2s, so the first audit during a cold start may be
  swallowed. This is fine — it's a telemetry path, not a control path.
- **`mcp.reachable=false` after deploy.** Means the heartbeat couldn't open
  an MCP session. Most often the Cloud Run secret binding for `dt-environment`
  or `dt-platform-token` isn't resolving. Check the heartbeat span's
  `mcp.error` attribute; missing config shows up as `config: 'DT_ENVIRONMENT'`.
- **Spans not landing on `sentinelds-sentinel`.** The OTLP exporter needs
  `DYNATRACE_API_URL` and `DYNATRACE_API_TOKEN`. Without them, spans are
  dropped silently — `init_tracing` succeeds but the exporter has nowhere to
  ship to.
