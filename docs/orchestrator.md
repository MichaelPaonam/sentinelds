# Orchestrator (Cloud Run)

The `sentinelds-orchestrator` service is an ADK web application built with
`get_fast_api_app(web=True)`. It runs a `SequentialAgent` pipeline
(research → feature → modeling). Each step is a `RemoteA2aAgent` that calls
one of the three A2A Cloud Run sub-agent services.

Deploy with `deploy_orchestrator.sh` at the repo root. That script generates
`src/orchestrator/agent.py`, `src/main.py`, and a `Dockerfile` at deploy time,
then removes them on exit.

---

## No agent card on the orchestrator (expected)

`GET /.well-known/agent-card.json` on the orchestrator returns **404**. This is
**expected behavior**, not a misconfiguration.

| Check | Orchestrator | A2A sub-agents (research / feature / modeling) |
|---|---|---|
| `GET /.well-known/agent-card.json` | **404** — not an A2A service | **200** — JSON agent card |
| Root agent type | `SequentialAgent` | `RemoteA2aAgent` proxying a local `SequentialAgent` |
| Built with | `get_fast_api_app` | `to_a2a()` |

The agent-card well-known URL is only served by services wrapped with ADK's
`to_a2a()`. The orchestrator coordinates remote agents; it does not expose
itself as an A2A peer.

Similarly, `GET /apps/orchestrator/app-info` may respond with
**"Root agent is not an LlmAgent"**. The ADK web UI introspection path assumes
an `LlmAgent` root; our pipeline root is a `SequentialAgent` of
`RemoteA2aAgent` children.

---

## Agent cards on sub-agents

Each sub-agent Cloud Run service publishes its card at the same path:

```
GET https://<sub-agent-service-url>/.well-known/agent-card.json
```

| Cloud Run service | Agent card env var (base URL, no path suffix) |
|---|---|
| `sentinelds-a2a-research` | `RESEARCH_AGENT_CARD_BASE_URL` |
| `sentinelds-a2a-feature` | `FEATURE_AGENT_CARD_BASE_URL` |
| `sentinelds-a2a-modeling` | `MODELING_AGENT_CARD_BASE_URL` |

The orchestrator passes
`{BASE_URL}/.well-known/agent-card.json` to each `RemoteA2aAgent` at startup.
Set the three `*_AGENT_CARD_BASE_URL` variables when deploying the orchestrator
(see `deploy_orchestrator.sh`).

Sub-agent cards rewrite the `url` field to match the inbound host on Cloud Run
(via `AgentCardURLMiddleware` in each `a2a_*/main.py`).

---

## Orchestrator endpoints

| Endpoint | Notes |
|---|---|
| `GET /` | ADK web UI (chat + trace viewer) |
| `GET /health` | Liveness |
| `POST /run` | Run the pipeline; requires a session and `appName: "orchestrator"` |
| Session routes | ADK session create/list/delete (see ADK FastAPI docs) |
| `GET /.well-known/agent-card.json` | **404** — see above |
| `GET /apps/orchestrator/app-info` | May report non-`LlmAgent` root — see above |

Example base URL (demo deployment):

```
https://sentinelds-orchestrator-463175257419.europe-west4.run.app
```

---

## Local vs Cloud Run

| Component | Local dev | Cloud Run |
|---|---|---|
| Full pipeline (in-process) | `src/agents/agent.py` + `e2e/run_demo.py` | — |
| Orchestrator UI + remote A2A | — | `sentinelds-orchestrator` |
| Individual agents as A2A | `uvicorn a2a_agents.a2a_*` | `sentinelds-a2a-*` services |

For local orchestrator testing, point the three `*_AGENT_CARD_BASE_URL` values
at running local A2A services (default `http://localhost:8080` in generated
`src/orchestrator/agent.py`).
