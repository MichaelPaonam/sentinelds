# Repository Guidelines

## Project Structure & Module Organization
`sentinelds` is currently a planning-stage repository. The active top-level files are:

- `README.md` for the project summary, demo scope, and milestones.
- `PLAN.md` for the architecture, threat model, prerequisites, and delivery schedule.
- `LICENSE` and `.gitignore` for repo policy and local artifact exclusions.

When implementation lands, keep the documented architecture intact: Research, Feature Engineering, Modelling, and Sentinel components should live in clearly separated modules. Store large datasets, traces, models, and demo recordings in ignored paths such as `data/`, `traces/`, `models/`, and `demo/recordings/`.

## Karpathy-Inspired Coding & Execution Principles
These four core principles combat common LLM coding pitfalls (such as wrong assumptions, overengineering, or side-effect edits). Always apply them to ensure surgical, clean, and senior-level implementation:

- **Think Before Coding**: Don't assume. Don't hide confusion. Surface tradeoffs. State assumptions explicitly. If multiple interpretations exist, ask rather than pick silently.
- **Simplicity First**: Write the minimum code that solves the problem. Nothing speculative. No single-use abstractions or unused configurability. If 200 lines could be 50, rewrite it.
- **Surgical Changes**: Touch only what you must. Clean up only your own mess. Match existing codebase style. Every changed line must trace directly to the requested task. Do not refactor adjacent code.
- **Goal-Driven Execution**: Define clear success criteria (e.g. tests, specific metrics). State a brief step-by-step plan before execution, and loop independently until verified.

## Build, Test, and Development Commands
No runnable application, build script, or test suite is checked in yet. Until scaffolding is added, contributors should use:

- **Check Knowledge Base FIRST**: Always view and check the offline knowledge base located at `$HOME\Projects\sentinelds-KB` (especially `development_operations.md` and `README.md`) before running any tasks.
- **Knowledge Base Synchronization**: Whenever there is a documentation update in this project repository (such as modifications to `README.md`, `PLAN.md`, `GEMINI.md`, `AGENTS.md`, or files under the `docs/` folder), you MUST immediately propagate and synchronize those changes to the corresponding files and index inside the offline knowledge base at `$HOME\Projects\sentinelds-KB` to keep them perfectly in sync.
- **Python Executable Rule**: On Windows, always invoke Python tools via the local virtual environment: `.venv\Scripts\python.exe` (or using `uv run`). Never run raw or global `python` commands.
- **Dependency & Tool Checks**: Always check `pyproject.toml` and `uv.lock` before executing commands to verify that the tool is actually installed in the workspace (e.g. `ruff` is NOT installed in `uv.lock` or `pyproject.toml` despite having configuration sections; do not run `ruff`). Use `.venv\Scripts\mypy` for static typing and `.venv\Scripts\pytest` for tests.
- `git status` to verify a clean working tree before and after changes.
- `Get-Content README.md` to review the current repo contract.
- `Get-Content PLAN.md` to confirm architecture and milestone assumptions.

Planned local tooling in `PLAN.md` is Python 3.11+, `uv` or `poetry`, Node.js 20+, `gcloud`, and Docker. Align new automation with that stack instead of introducing parallel tooling.

## Coding Style & Naming Conventions
Prefer Python-first conventions because the planned runtime is ADK + data-science tooling. Use 4-space indentation, `snake_case` for modules and functions, `PascalCase` for classes, and short, descriptive file names. Keep agent boundaries explicit in names such as `research_agent.py` or `sentinel_policy.py`. Favor small modules over monolithic notebooks or scripts.

## Testing Guidelines
Add tests alongside new code rather than deferring them. Use `tests/` with file names like `test_research_agent.py`. Cover agent orchestration, Sentinel pre-flight decisions, and telemetry emission paths first. If you add a test runner, standardize on one command and document it in `README.md`.

## Commit & Pull Request Guidelines
Recent history uses short, imperative messages such as `Update README repo layout` and `updated PLAN.md`. Keep commits focused and readable; mention the file or subsystem when useful. PRs should include a concise summary, linked issue or milestone, test evidence, and screenshots or trace captures for dashboard, telemetry, or demo-flow changes.

## Security & Configuration Tips
Do not commit `.env` files, service-account keys, OTLP tokens, MCP credentials, datasets, or model artifacts. Follow `.gitignore` for local outputs, and keep any security-sensitive demo setup documented in `PLAN.md` or `README.md` rather than hardcoded in source.
