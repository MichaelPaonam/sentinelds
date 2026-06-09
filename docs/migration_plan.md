# Migration Plan — Local stdio MCP → Remote Dynatrace MCP Server

**For:** Sonnet (or any implementer) executing the swap end-to-end.
**Owner of decision:** Michael (architecture confirmed 2026-06-09).
**Tracks against:** `docs/dynatrace-mcp-options.md` fallback tier 1 (transport swap).

---

## 1. Why this migration

The Sentinel Agent currently spawns `@dynatrace-oss/dynatrace-mcp-server@1.8.6` as a Node subprocess via `npx` over stdio (`src/sentinel/dynatrace_mcp.py:122`). That upstream package is in **maintenance mode** ([dynatrace-oss/dynatrace-mcp issue #496](https://github.com/dynatrace-oss/dynatrace-mcp/issues/496)); Dynatrace's active development is on the **remote MCP server** at:

```
https://{environment}.apps.dynatrace.com/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp
```

Source: <https://docs.dynatrace.com/docs/dynatrace-intelligence/dynatrace-mcp>.

We pre-committed to this swap as fallback tier 1 in `docs/dynatrace-mcp-options.md:179`. The transport abstraction in `dynatrace_session()` was designed for exactly this swap.

### What stays the same
- All public function signatures: `list_open_problems()`, `run_dql()`, `dynatrace_session()`, `DynatraceMCPConfig.from_env()`.
- `Sentinel.preflight()` and the entire observer pattern (`Sentinel.notify`, `SentinelSession`, `@sentinel_gate`) — transport-agnostic.
- All current tests in `tests/test_preflight.py` (they patch `list_open_problems` / `run_dql` directly, not the transport).

### What changes
- One file's body: `src/sentinel/dynatrace_mcp.py` swaps `stdio_client` for `streamablehttp_client`.
- `DynatraceMCPConfig` loses npm-runtime fields (`server_version`, `disable_telemetry`, `grail_budget_gb`); gains a derived `remote_url`.
- `tests/test_sentinel_mcp.py` config tests update to the new field set.
- One smoke script and the README's smoke-test list pick up a new entry.
- `.env.example` gets the new platform-token scope requirements documented.

---

## 2. Pre-flight checks before touching code

Run these to confirm the environment is ready. **Do not start step 3 until all four pass.**

```bash
# (a) Confirm DT_ENVIRONMENT and DT_PLATFORM_TOKEN are set
grep -E "^DT_(ENVIRONMENT|PLATFORM_TOKEN)=" .env

# (b) Confirm the mcp Python SDK has streamablehttp_client (it does — already in deps)
PYTHONPATH=src uv run python -c "from mcp.client.streamable_http import streamablehttp_client; print('ok')"

# (c) Current tests are green on the current branch
uv run python -m pytest tests/test_sentinel_mcp.py tests/test_preflight.py -v

# (d) Branch off the current PR's base (phase-three)
git fetch origin
git checkout -b feat/remote-mcp origin/phase-three
```

**Token scope requirement.** The remote MCP gateway needs the `DT_PLATFORM_TOKEN` to carry these scopes (per [remote-mcp-migration.md](https://github.com/dynatrace-oss/dynatrace-mcp/blob/main/docs/remote-mcp-migration.md)):

- `mcp-gateway:servers:invoke` — required
- `mcp-gateway:servers:read` — required
- `storage:buckets:read`, `storage:events:read`, `storage:logs:read` — for `execute_dql`
- `davis:analyzers:read`, `davis:analyzers:execute` — only if Sentinel ever calls Davis Copilot tools (**not needed for v0**)

Action: tell the user (Michael) to verify the existing `DT_PLATFORM_TOKEN` has the two `mcp-gateway:*` scopes. **If unsure, stop and ask** — token regeneration is a manual Dynatrace UI action.

---

## 3. Code changes — step by step

### 3.1 Spike script (write first, run before refactoring)

**Create** `src/smoke/sentinel_remote_mcp_smoke.py`:

- Loads `DT_ENVIRONMENT` and `DT_PLATFORM_TOKEN` from env (via `dotenv.load_dotenv()` like the existing smokes do — see `src/smoke/sentinel_mcp_smoke.py:1-30` for the pattern).
- Constructs `REMOTE_URL = f"{DT_ENVIRONMENT.rstrip('/')}/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp"`.
- Opens a session:
  ```python
  from mcp.client.streamable_http import streamablehttp_client
  from mcp import ClientSession

  headers = {"Authorization": f"Bearer {platform_token}"}
  async with streamablehttp_client(remote_url, headers=headers) as (read, write, _close):
      async with ClientSession(read, write) as session:
          await session.initialize()
          # 1. list tools to confirm list_problems/execute_dql are present
          tools = await session.list_tools()
          # 2. call list_problems with status="ACTIVE", no entity
          # 3. call execute_dql with a tight DQL: fetch events, from:now()-1m | limit 1
  ```
- Prints the raw `CallToolResult.content[0].text` for both calls. **Do not parse yet** — we need to confirm the response shape matches the local server before reusing the parser.

Run it:

```bash
PYTHONPATH=src uv run python -m smoke.sentinel_remote_mcp_smoke
```

**Acceptance gate before continuing:**
1. Tool list contains `list_problems` and `execute_dql` with those exact names.
2. `list_problems` returns either a JSON envelope `{"problems": [...]}` or the empty-result sentinel `"No problems found"` (matches local server behavior pinned in `docs/dynatrace-mcp-notes.md:38`).
3. `execute_dql` returns a markdown-fenced JSON list (matches `docs/dynatrace-mcp-notes.md:88`).

**If any of those three fail:** stop, capture the actual response in a comment in the smoke script, and surface to Michael. The shape may have shifted on the remote server — we'd then need to update `_parse_text_content` accordingly. Do not proceed to 3.2 until shapes match.

### 3.2 Refactor `src/sentinel/dynatrace_mcp.py`

**Goal:** replace transport, keep every public name and signature identical.

#### 3.2.1 Imports

Replace lines 41-43:

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent
```

With:

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, TextContent
```

(Drop `StdioServerParameters`. Keep `ClientSession`, `CallToolResult`, `TextContent`.)

#### 3.2.2 `DynatraceMCPConfig` (lines 46-91)

Replace the entire dataclass with:

```python
@dataclass(frozen=True)
class DynatraceMCPConfig:
    """Configuration for the Dynatrace **Remote** MCP Server.

    Connection is HTTP (Streamable HTTP transport) to the Dynatrace-hosted
    MCP gateway at ``{environment}/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp``.
    Auth is a bearer Platform Token. No local Node subprocess is spawned.

    Construct via :meth:`from_env`. The platform token is forwarded as a
    Bearer header on every MCP request and is never logged.
    """

    environment: str
    """Dynatrace tenant URL, e.g. ``https://abc12345.apps.dynatrace.com``."""

    platform_token: str
    """Platform Token. Sent as ``Authorization: Bearer <token>``; never logged.

    Required scopes: ``mcp-gateway:servers:invoke``, ``mcp-gateway:servers:read``,
    plus the relevant ``storage:*:read`` scopes for the DQL queries the
    Sentinel pre-flight runs. See ``docs/dynatrace-mcp-options.md``.
    """

    @property
    def remote_url(self) -> str:
        """Full Streamable-HTTP URL of the remote MCP gateway."""
        return (
            f"{self.environment.rstrip('/')}"
            "/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp"
        )

    @classmethod
    def from_env(cls) -> "DynatraceMCPConfig":
        """Read ``DT_ENVIRONMENT`` and ``DT_PLATFORM_TOKEN`` from os.environ.

        Both are required. Raises :class:`KeyError` with a clear message if
        either is unset — the Sentinel Agent must fail fast in that case so
        the demo never silently disables the gate.
        """
        try:
            environment = os.environ["DT_ENVIRONMENT"]
            platform_token = os.environ["DT_PLATFORM_TOKEN"]
        except KeyError as missing:
            raise KeyError(
                f"Required Dynatrace MCP env var {missing} is not set. "
                "See docs/dynatrace-mcp-options.md and .env.example."
            ) from missing
        return cls(environment=environment, platform_token=platform_token)
```

**Removed fields:** `server_version`, `disable_telemetry`, `grail_budget_gb`. None of these apply to the remote server (no subprocess to configure; Grail budget is set on the tenant, not per call).

#### 3.2.3 Drop `_server_params` (lines 94-109)

Delete the entire `_server_params` function. It was stdio-specific.

#### 3.2.4 Rewrite `dynatrace_session` (lines 112-125)

Replace with:

```python
@asynccontextmanager
async def dynatrace_session(
    cfg: DynatraceMCPConfig,
) -> AsyncIterator[ClientSession]:
    """Open a long-lived MCP session against the Dynatrace **Remote** MCP server.

    The Sentinel Agent should open this once at startup and reuse the yielded
    session for every pre-flight call — establishing a fresh HTTP connection
    per call would dwarf the actual tool-call latency.

    Auth is via ``Authorization: Bearer <DT_PLATFORM_TOKEN>``. The token is
    forwarded on every request by the Streamable HTTP transport.
    """
    headers = {"Authorization": f"Bearer {cfg.platform_token}"}
    async with streamablehttp_client(cfg.remote_url, headers=headers) as (
        read,
        write,
        _close,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session
```

Notes for implementer:
- `streamablehttp_client` yields a 3-tuple `(read, write, close_callback)`. We bind the third to `_close` and ignore it — `ClientSession` handles teardown via the outer `async with`.
- The `headers` kwarg name on `streamablehttp_client` is `headers` per the `mcp` SDK. **Verify this in the spike (3.1)** — if the SDK version pinned in `pyproject.toml` uses a different kwarg name (some versions take a `httpx_client_factory`), adjust accordingly. The spike will fail loudly if the kwarg is wrong.

#### 3.2.5 `_parse_text_content`, `list_open_problems`, `run_dql`

**Do not touch these functions.** They operate on `CallToolResult` and are transport-agnostic. The existing parsing logic (markdown-fenced JSON, empty-result sentinels) was confirmed against the local server but the remote server is documented to return the same shapes (it's the same Dynatrace tools surface, just hosted).

**If the spike (3.1) showed a shape mismatch**, add a fix here, but log it loudly in the diff so reviewers know.

#### 3.2.6 Module docstring (lines 1-30)

Update the docstring to reflect the transport change. Replace the opening with:

```python
"""Dynatrace MCP client for the Sentinel Agent.

Connects to the **Dynatrace Remote MCP Server** (Streamable HTTP transport)
at ``{DT_ENVIRONMENT}/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp``,
authenticated with a Platform Token (``DT_PLATFORM_TOKEN``).

The Sentinel pre-flight gate uses two tools — ``list_problems`` and
``execute_dql`` — surfaced as plain async Python functions returning
``list[dict]``.

Why remote (full reasoning in ``docs/dynatrace-mcp-options.md`` and
``docs/migration_plan.md``):

* the previous local server (``@dynatrace-oss/dynatrace-mcp-server``) is in
  maintenance mode upstream; Dynatrace's active path is the remote server.
* no Node subprocess in our process tree — cleaner Cloud Run images, no
  ``npx`` cold start.
* same tool names (``list_problems``, ``execute_dql``), so the Sentinel
  pre-flight code in ``preflight.py`` is unchanged.
* auth via env-loaded ``DT_PLATFORM_TOKEN`` (no hardcoded credentials).

Response shapes are documented in ``docs/dynatrace-mcp-notes.md``. Every tool
call returns a ``CallToolResult`` whose ``.content`` is a single
``TextContent`` block whose ``.text`` is a JSON string (or markdown-fenced
JSON for ``execute_dql``). ``list_problems`` returns ``{"problems": [...]}``;
``execute_dql`` returns a bare list of records inside a ``\`\`\`json\`\`\``
fence. We pull those out and return them.

Fallback ladder (if the remote server is unreachable during the demo):
direct REST → fixture replay. Both preserve the function signatures below.
See ``docs/dynatrace-mcp-options.md`` "Fallback ladder".
"""
```

### 3.3 Update `tests/test_sentinel_mcp.py`

Read the file first (~245 lines). The structure is:

- `TestDynatraceMCPConfig` — tests for `from_env` and the (now-deleted) `_server_params`.
- `TestParseTextContent` — tests the parser. **Leave untouched.**
- `TestListOpenProblems`, `TestRunDQL` — call the public functions with a mocked `ClientSession`. **Leave untouched.**

Edits in `TestDynatraceMCPConfig`:

- Tests that construct `DynatraceMCPConfig` with `server_version=...`, `disable_telemetry=...`, `grail_budget_gb=...` (around line 61): drop those kwargs. The constructor now only takes `environment` and `platform_token`.
- Any test that imports `_server_params` or asserts on its return value: **delete the entire test method**. `_server_params` no longer exists. Add a `# Removed: _server_params no longer exists post remote-MCP migration` comment in its place if it makes the diff easier to read.
- Add a small new test asserting `cfg.remote_url` returns the expected URL:
  ```python
  def test_remote_url_construction(self):
      cfg = DynatraceMCPConfig(
          environment="https://abc12345.apps.dynatrace.com",
          platform_token="secret",
      )
      self.assertEqual(
          cfg.remote_url,
          "https://abc12345.apps.dynatrace.com/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp",
      )

  def test_remote_url_strips_trailing_slash(self):
      cfg = DynatraceMCPConfig(
          environment="https://abc12345.apps.dynatrace.com/",
          platform_token="secret",
      )
      self.assertTrue(cfg.remote_url.startswith("https://abc12345.apps.dynatrace.com/platform-reserved"))
      self.assertNotIn("//platform-reserved", cfg.remote_url)
  ```

Run after editing:

```bash
uv run python -m pytest tests/test_sentinel_mcp.py -v
```

All tests must pass. **`tests/test_preflight.py` must remain untouched and pass** — it patches `list_open_problems` / `run_dql` symbolically and is transport-agnostic.

### 3.4 Update `src/smoke/sentinel_mcp_smoke.py`

This script connects via the old stdio transport. Two options:

**Option A (recommended) — keep it, rename it.** Rename to `sentinel_local_mcp_smoke.py` and add a banner comment that it's now the legacy / fallback verification path (still useful for offline dev if Michael ever installs the local server again). Keep imports from `dynatrace_mcp` — wait, those imports break because we removed `_server_params` and changed the config shape. So:

**Option B (cleaner) — delete `sentinel_mcp_smoke.py`** and keep only the new `sentinel_remote_mcp_smoke.py` from step 3.1. The local stdio path is no longer supported; resurrect it from git history if ever needed.

**Pick Option B.** Reasons:
- Avoids carrying two parallel smoke scripts that drift.
- The fallback ladder in `docs/dynatrace-mcp-options.md` no longer puts local stdio as tier 1 — it's superseded.
- Git history preserves the old script if someone needs it.

Action:
```bash
git rm src/smoke/sentinel_mcp_smoke.py
```

And ensure `src/smoke/sentinel_remote_mcp_smoke.py` is the canonical MCP smoke. (Step 3.1 already created it as a spike — promote it to production-quality: clean output, exit codes, error messages.)

### 3.5 Update `.env.example`

Replace the existing MCP block (currently around the `DT_ENVIRONMENT` / `DT_PLATFORM_TOKEN` lines) with:

```bash
# Dynatrace Remote MCP Server (used by the Sentinel Agent's pre-flight gate)
# Connects to {DT_ENVIRONMENT}/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp
# via Streamable HTTP transport.
#
# DT_PLATFORM_TOKEN must carry these scopes:
#   - mcp-gateway:servers:invoke  (required)
#   - mcp-gateway:servers:read    (required)
#   - storage:buckets:read, storage:events:read, storage:logs:read  (for execute_dql)
# See docs/dynatrace-mcp-options.md and docs/migration_plan.md.
# DT_ENVIRONMENT="https://<your-tenant-id>.apps.dynatrace.com"
# DT_PLATFORM_TOKEN="<your-platform-token>"
```

(Drop the comment line referencing the local subprocess, since there is no subprocess anymore.)

### 3.6 Update `pyproject.toml`

Check whether `mcp` is pinned. If the version pinned predates `mcp.client.streamable_http` (added in `mcp` Python SDK ~v1.1+), bump it. Run:

```bash
PYTHONPATH=src uv run python -c "import mcp; print(mcp.__version__)"
```

If `< 1.1.0`, edit `pyproject.toml`'s `mcp` dep to `mcp>=1.2.0` and run `uv sync`. If `>= 1.1.0`, leave it alone.

(The pre-flight check 2(b) above was supposed to confirm this — if it failed, this step is where we fix it.)

### 3.7 Update docs

#### 3.7.1 `docs/dynatrace-mcp-options.md`

- Section "Recommendation" (line 95): rewrite the lead paragraph to say the recommendation is now **Remote MCP Server**, not Local. Move the Local section's bullets into "Why we don't use Local anymore" and shorten.
- "Fallback ladder" (line 175): remove tier 1 (transport swap to remote) — remote is now primary. Renumber: tier 1 = direct REST, tier 2 = fixture replay.

Keep this minimal — the file's job is to record the decision rationale, and the rationale shifted by one tier; not a full rewrite.

#### 3.7.2 `docs/dynatrace-mcp-notes.md`

Add a new note at the top of the file (above section 1):

```markdown
> **Transport update (2026-06-09).** The Sentinel client now connects to the
> Dynatrace **Remote** MCP Server via Streamable HTTP, not the local Node
> stdio subprocess. The response shapes documented below were captured
> against the local server v1.8.6 and are confirmed to match the remote
> server (verified during the migration spike — see
> `docs/migration_plan.md`). If you observe a shape difference on the
> remote path, update this file with a verbatim capture under the affected
> tool's section.
```

Leave everything else in the file unchanged — the response shapes are still the contract.

#### 3.7.3 `README.md`

In the "Required environment variables" section (around line 207-225 in the current README):

- The block already mentions `DT_PLATFORM_TOKEN` with `environment-api:problems:read, storage:query:read` scopes. **Update those scopes** to:
  ```
  mcp-gateway:servers:invoke, mcp-gateway:servers:read,
  storage:buckets:read, storage:events:read, storage:logs:read
  ```
- The two-tokens callout (block quote starting "Two separate Dynatrace tokens are required") needs the line about the platform token's purpose updated to "used by the Sentinel Agent to query the **Remote** Dynatrace MCP Server (`list_problems`, `execute_dql`)".

In the smoke-tests block (lines 235-241):

- Remove the line `PYTHONPATH=src uv run python -m smoke.sentinel_mcp_smoke` (script deleted).
- Add `PYTHONPATH=src uv run python -m smoke.sentinel_remote_mcp_smoke      # remote MCP connectivity + Sentinel preflight`.

In the Repo layout block (line 167):

- Update the comment on `dynatrace_mcp.py` from `← Dynatrace MCP client (list_open_problems, run_dql)` to `← Dynatrace Remote MCP client (list_open_problems, run_dql)`.

In `docs/` listing (line 144):

- Add `│   └── migration_plan.md                    ← stdio → remote MCP migration plan` under the existing `dynatrace-mcp-options.md` entry.

#### 3.7.4 `CLAUDE.md`

Don't touch unless something concretely changes for future Claude sessions. The migration doesn't change build/run commands at the project-instruction level.

---

## 4. Validation gates (run all, in order)

After all edits, run these from the repo root:

```bash
# 1. Lint + format
uv run python -m ruff check src tests
uv run python -m ruff format --check src tests

# 2. Unit tests (existing)
uv run python -m pytest tests/ -v

# 3. Type-check the touched module
uv run python -c "import sentinel.dynatrace_mcp" 2>&1 | grep -v "^$" || echo "import ok"

# 4. Smoke against live tenant (requires DT_ENVIRONMENT + DT_PLATFORM_TOKEN with new scopes)
PYTHONPATH=src uv run python -m smoke.sentinel_remote_mcp_smoke

# 5. Observer pattern smoke (end-to-end with attack server)
#    Terminal 1:
#    uvicorn attack_server.server:app --port 8001 --app-dir src
#    Terminal 2:
PYTHONPATH=src uv run python -m smoke.observer_smoke
```

**All five must succeed before opening a PR.** If step 4 fails with auth errors, the most likely cause is missing `mcp-gateway:*` scopes on the platform token — that's a token-regen issue, not a code bug; surface to Michael.

---

## 5. PR shape

- **Branch:** `feat/remote-mcp` (created in step 2)
- **Base:** `phase-three`
- **Title:** `Migrate Sentinel MCP client from local stdio to remote streamable HTTP`
- **Body** (use the repo's `pull_request_template.md`):
  - **Summary:** One sentence — "Sentinel Agent now connects to the Dynatrace Remote MCP Server via Streamable HTTP; drops the Node subprocess entirely."
  - **Changes:** Bullet the files touched (5–8 bullets).
  - **Technical Notes:** Link to this `migration_plan.md` and `dynatrace-mcp-options.md` for the full rationale.
  - **Validation:** Paste the output of all five gates from section 4.
  - **Metrics/Results:** Latency comparison if cheap to measure: capture `list_problems` round-trip time before (stdio: ~50–100ms) and after (HTTP: ~150–300ms expected). If the new path is >500ms, surface as a concern.
  - **Related Issue:** Reference the maintenance-mode issue: <https://github.com/dynatrace-oss/dynatrace-mcp/issues/496>.

Do NOT include `--draft` unless Michael asks for one.

---

## 6. Things to NOT do

- **Don't rewrite `preflight.py`.** The whole point of the transport abstraction is that it doesn't change.
- **Don't rewrite the observer pattern.** `Sentinel.notify`, `SentinelSession`, `@sentinel_gate` are transport-agnostic.
- **Don't touch the OTLP exporter** (`src/observability/otel.py`). That's a different Dynatrace integration (telemetry ingest) using a classical API token, not the platform token.
- **Don't expand scope** to add new MCP tools (e.g. `find_entity_by_name`, Davis Copilot). The hackathon demo uses exactly `list_problems` + `execute_dql`. Adding tools is post-hackathon work.
- **Don't break the fallback story.** Direct REST and fixture replay must still be reachable as tiers 1 and 2 of the new fallback ladder. Code-wise that means keep `list_open_problems` / `run_dql` signatures stable so a future direct-REST implementation can drop in.
- **Don't commit the platform token.** It's in `.env`, which is gitignored. Confirm `git status` is clean of `.env` before pushing.

---

## 7. Rollback

If the migration breaks the demo path mid-week:

```bash
git revert <merge commit sha>   # against phase-three
```

The local stdio path is recoverable from git history (`src/smoke/sentinel_mcp_smoke.py` and the old `dynatrace_mcp.py` body). The Node `npx` runtime is reproducible (still publishable on npm even in maintenance mode). Worst case, we ship the demo on the local path and document the remote-path migration as post-hackathon work in `PLAN.md` section 8.

---

## 8. Time estimate

- Step 2 (pre-flight): 5 min
- Step 3.1 (spike): 30 min — most of the risk lives here
- Steps 3.2–3.7 (refactor + tests + docs): 60 min
- Step 4 (validation gates): 15 min
- Step 5 (PR): 10 min

**Total:** ~2 hours if the spike succeeds first try; +1 hour if response shapes differ on the remote server and `_parse_text_content` needs adjustment.

---

## 9. Open questions for Michael (resolve before starting if any apply)

1. **Token scopes.** Does the existing `DT_PLATFORM_TOKEN` already have `mcp-gateway:servers:invoke` and `mcp-gateway:servers:read`? If unknown, regenerate the token with all required scopes before step 3.1.
2. **Demo timing.** This migration touches the demo-critical path. If we're inside the M2 → M3 window (Jun 8 → Jun 10), the bias should shift to "ship local stdio for the video, do remote post-submission." As of 2026-06-09, M3 (video) is tomorrow — **this migration is risky right now**. Confirm with Michael whether to proceed pre-video or defer to a post-submission cleanup PR.
3. **Latency budget.** The Sentinel A2 pre-flight runs before training. HTTP round-trip will add ~100–200ms vs stdio. Confirm that's still inside the demo's "feels instant" budget. (For A1, it's irrelevant — local-first observer pattern.)
