# Dynatrace MCP — observed response shapes

This file pins the JSON shapes returned by the Dynatrace MCP Server tools that the [Sentinel Agent](../src/sentinel/dynatrace_mcp.py) depends on. The shapes below are starting placeholders derived from the upstream `@dynatrace-oss/dynatrace-mcp-server` README and Dynatrace API docs; replace each block with a verbatim capture from the live tenant the first time `src/smoke/sentinel_mcp_smoke.py` runs successfully.

> **Why this file exists.** Issue [#23](https://github.com/MichaelPaonam/sentinelds/issues/23) requires us to document response shapes so downstream defense logic can be built against a stable contract. The decision to pick the Local Dynatrace MCP Server (and the fallbacks if it fails) is in [`dynatrace-mcp-options.md`](dynatrace-mcp-options.md).

---

## How the MCP transport wraps the payload

Every Dynatrace MCP tool call returns a `CallToolResult` whose `content` field is a list of typed content blocks. The Dynatrace server returns a single `TextContent` block whose `.text` is a JSON string:

```python
result = await session.call_tool("list_problems", {"entity": entity_id, "status": "OPEN"})
# result.content == [TextContent(type="text", text='{"problems": [...]}')]
payload = json.loads(result.content[0].text)
```

If the server ever returns multiple content blocks or a non-text block, `dynatrace_mcp.py`'s parser raises rather than silently dropping data — confirm in the spike.

---

## `list_problems` — shape

**Tool args:** `{"entity": "<DT_ENTITY_ID>", "status": "OPEN"}`

**Expected `result.content[0].text` (JSON):**

```jsonc
{
  "problems": [
    {
      "problemId": "<opaque-id>",
      "displayId": "P-1234",
      "title": "High failure rate",
      "severity": "ERROR",                  // one of: AVAILABILITY, ERROR, PERFORMANCE,
                                            //         RESOURCE_CONTENTION, CUSTOM_ALERT,
                                            //         MONITORING_UNAVAILABLE, INFO
      "status": "OPEN",                     // OPEN | CLOSED
      "startTime": "2026-06-01T12:34:56Z",
      "endTime": null,
      "affectedEntities": [
        { "entityId": "<DT_ENTITY_ID>", "name": "sentinelds-workspace" }
      ],
      "rootCauseEntity": null,
      "tags": [{ "key": "agent.name", "value": "Research Agent" }]
    }
    // …more problems
  ]
}
```

**Notes / open questions to confirm in the spike:**
- Whether the wrapper key is `problems` (REST API style) or the array is returned at the top level.
- Whether `severity` is the string above or the numeric `severityLevel` from the v2 problems API.
- Whether `affectedEntities[].entityId` matches the workspace id we passed in (it should — that's the filter).

When confirmed, paste the verbatim capture below this block and delete the placeholder above.

---

## `execute_dql` — shape

**Tool args:** `{"query": "<DQL string with explicit timeframe>"}`

**Sentinel pre-flight DQL (v0):**

```dql
fetch events, from:now()-5m
| filter event.kind == "BIZ_EVENT" and event.type == "sentinelds.attack.detected"
| filter dt.entity.workspace == "<DT_ENTITY_ID>"
| fields severity, attack_id, agent
| limit 10
```

**Expected `result.content[0].text` (JSON):**

```jsonc
{
  "records": [
    {
      "timestamp": "2026-06-01T12:34:56Z",
      "severity": "high",                   // emitted by sentinelds attack detectors
      "attack_id": "A1",                    // A1 = indirect prompt injection
      "agent": "Research Agent"
    }
  ],
  "metadata": {
    "scannedRecords": 0,
    "scannedBytes": 0,
    "scannedDataPoints": 0,
    "executionTimeMilliseconds": 0,
    "grailQueryBudgetUsageGb": 0
  }
}
```

**Notes / open questions to confirm in the spike:**
- The wrapper keys (`records` / `metadata`) — Grail responses sometimes use `result` / `extras` depending on API surface.
- Whether per-row keys are exactly the column names from the `fields` clause (case-sensitive).
- Whether `metadata.grailQueryBudgetUsageGb` is the canonical name for the GB-scanned counter (we use it to throttle the pre-flight).

When confirmed, paste the verbatim capture below this block and delete the placeholder above.

---

## Auth env vars consumed by the MCP subprocess

| Env var | Purpose | Required? |
|---|---|---|
| `DT_ENVIRONMENT` | Tenant URL, e.g. `https://abc12345.apps.dynatrace.com` | yes |
| `DT_PLATFORM_TOKEN` | Platform Token; never logged | yes (if not using OAuth) |
| `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` | OAuth client credentials | only if Platform Token unset |
| `DT_SSO_URL` | SSO override URL | optional |
| `DT_MCP_DISABLE_TELEMETRY` | Set to `"true"` to opt out of upstream telemetry | optional, we set it |
| `DT_GRAIL_QUERY_BUDGET_GB` | GB-scanned cap (default 1000; we set 50 for hackathon) | optional |

The Python process inherits **only** these env vars into the subprocess (see `dynatrace_mcp.py:_server_params`). It never logs `DT_PLATFORM_TOKEN`.

---

## Spike checklist (issue #23 acceptance gate)

- [ ] `uv run python -m src.smoke.sentinel_mcp_smoke` exits 0 against a live tenant
- [ ] `list_problems` capture pasted above
- [ ] `execute_dql` capture pasted above
- [ ] Both response shapes parse cleanly into `list[dict]` via `dynatrace_mcp.py`
- [ ] If any tier of the [fallback ladder](dynatrace-mcp-options.md#fallback-ladder-per-issue-23-risk-note) had to be used, decision recorded here with reason
