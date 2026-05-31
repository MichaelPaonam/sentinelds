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

**Tool args:** `{"status": "ACTIVE", "entity": "<DT_ENTITY_ID>"}`

> **Spike finding (2026‑06‑01, server v1.8.6).** The MCP server rejects
> `status: "OPEN"` with `MCP error -32602` and validates against
> `{"ACTIVE", "CLOSED", "ALL"}`. The Sentinel client sends `"ACTIVE"`. The
> Dynatrace v2 problems REST API still uses `"OPEN"` / `"CLOSED"` — the MCP
> layer normalises to its own vocabulary. Also: passing an empty-string
> ``entity`` is rejected, so the client omits the key entirely when no
> workspace id is set (useful on a fresh trial tenant before the workspace
> entity exists in Smartscape).
>
> **Empty-result sentinel.** When the call returns zero matches, the server
> emits the bare text ``"No problems found"`` instead of a JSON envelope.
> ``dynatrace_mcp._parse_text_content`` recognises that and yields an empty
> list. Confirmed against the trial tenant on 2026‑06‑01.

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

**Tool args:** `{"dqlStatement": "<DQL string with explicit timeframe>"}`

> **Spike finding (2026‑06‑01, server v1.8.6).** The argument key is
> ``dqlStatement``, not ``query`` — the natural name is rejected with
> `MCP error -32602: expected string, received undefined`.
>
> **Records are markdown-fenced JSON, not raw JSON.** The server returns a
> markdown document framed as user-facing copy with a `\`\`\`json … \`\`\``
> code fence containing a bare list of record objects (no ``records`` /
> ``metadata`` envelope). Verbatim capture from the trial tenant:
>
> ```
> 📊 **DQL Query Results**
>
> - **Scanned Records:** 41
> - **Scanned Bytes:** 0.00 GB (Session total: 0.00 GB / 50 GB budget, 0.0% used)
>
> 📋 **Query Results**: (1 records) — rendered by the MCP App UI below.
>
> > ℹ️ The MCP App is rendering the results interactively. Do NOT generate
> > Mermaid diagrams, ASCII charts, or markdown tables from this data.
> ```json
> [
>   {
>     "event.type": null,
>     "timestamp": "2026-05-31T21:39:51.583000000Z"
>   }
> ]
> ```
> ```
>
> ``dynatrace_mcp._parse_text_content`` extracts the fenced block before
> ``json.loads``. The metadata text (``scannedBytes`` / budget usage) is
> dropped — expose it in a follow-up issue if Sentinel needs to throttle on
> Grail budget.

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

- [x] **Node.js ≥ 22.10** on `PATH` before running the smoke. The MCP server uses `webidl.util.markAsUncloneable` from `undici`, which is a Node 22+ API; Node 20 fails at server startup with a `TypeError`. With `nvm`: `nvm install 22 && nvm use 22`.
- [x] `uv run python -m src.smoke.sentinel_mcp_smoke` exits 0 against a live tenant *(2026‑06‑01, trial tenant `cjw98236.apps.dynatrace.com`)*
- [x] `list_problems` capture pinned above (zero-result sentinel `"No problems found"`)
- [x] `execute_dql` capture pinned above (markdown-fenced bare list)
- [x] Both response shapes parse cleanly into `list[dict]` via `dynatrace_mcp.py`
- [ ] If any tier of the [fallback ladder](dynatrace-mcp-options.md#fallback-ladder-per-issue-23-risk-note) had to be used, decision recorded here with reason — *not used; primary path (Local Dynatrace MCP Server v1.8.6) shipped*
