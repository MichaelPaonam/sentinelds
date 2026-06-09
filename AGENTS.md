# Repository Guidelines

## Project Structure & Module Organization
`sentinelds` is currently a planning-stage repository. The active top-level files are:

- `README.md` for the project summary, demo scope, and milestones.
- `PLAN.md` for the architecture, threat model, prerequisites, and delivery schedule.
- `DESIGN.md` for the dashboard and front-end retro-brutalist Terminal CLI design specifications.
- `LICENSE` and `.gitignore` for repo policy and local artifact exclusions.

When implementation lands, keep the documented architecture intact: Research, Feature Engineering, Modelling, and Sentinel components should live in clearly separated modules. Store large datasets, traces, models, and demo recordings in ignored paths such as `data/`, `traces/`, `models/`, and `demo/recordings/`.

## Karpathy-Inspired Coding & Execution Principles
To prevent guideline drift, the single source of truth for our development principles is located under our shared repository plugins:
- **Consolidated Coding Principles**: [.antigravitycli/plugins/sentinelds-guidelines/skills/karpathy_coding.md](file:///.antigravitycli/plugins/sentinelds-guidelines/skills/karpathy_coding.md)

All contributors and automated agents must adhere strictly to these four core guidelines:
1. **Think Before Coding**: Don't assume. Surface tradeoffs and ask clarifying questions instead of guessing.
2. **Simplicity First**: Write the minimum code required. Avoid speculative features or complex single-use abstractions.
3. **Surgical Changes**: Touch only what you must. Match existing style and do not refactor adjacent files.
4. **Goal-Driven Execution**: Define clear success criteria (tests, metrics) and execute a structured plan in a loop.

## Build, Test, and Development Commands
Execution rules and environment verification constraints are consolidated inside our shared pre-flight skill:
- **Execution & Pre-flight Rules**: [.antigravitycli/plugins/sentinelds-guidelines/skills/sentinelds_preflight.md](file:///.antigravitycli/plugins/sentinelds-guidelines/skills/sentinelds_preflight.md)

### Standard Workflow & Bootstrapping
1. **Check Knowledge Base FIRST**: Always view and check the offline knowledge base located at `$HOME/Projects/sentinelds-KB` (specifically `README.md` and `development_operations.md`) before running any tasks.
2. **Knowledge Base Bootstrapping**: If working on a fresh setup where `$HOME/Projects/sentinelds-KB` does not yet exist, the developer or agent MUST create this directory outside of the project folder on their local machine. When starting a new Antigravity (agy) session, the agent should proactively take permission from the user to read and write to `$HOME/Projects/sentinelds-KB` and bootstrap the folder by copying the guidelines, templates, and documentation files (such as those from `.antigravitycli/plugins/sentinelds-guidelines/` and the `docs/` directory) into the knowledge base to ensure safe and fully resolved references.
3. **Knowledge Base Synchronization**: Whenever there is a documentation update in this project repository (such as modifications to `README.md`, `PLAN.md`, `GEMINI.md`, `AGENTS.md`, or files under the `docs/` folder), you MUST immediately propagate and synchronize those changes to the corresponding files and index inside the offline knowledge base at `$HOME/Projects/sentinelds-KB` to keep them perfectly in sync.

### Platform-Specific Execution Cheat Sheet
Always run Python tools via the local virtual environment. Never invoke raw or global `python`/`pip` commands:

| Platform | Activate Env Command | Python Executable | Test Runner (`pytest`) | Type Checker (`mypy`) |
| :--- | :--- | :--- | :--- | :--- |
| **Windows (PowerShell)** | `.venv/Scripts/Activate.ps1` | `.venv/Scripts/python.exe` | `.venv/Scripts/pytest.exe` | `.venv/Scripts/mypy.exe` |
| **Windows (CMD)** | `.venv/Scripts/activate.bat` | `.venv/Scripts/python.exe` | `.venv/Scripts/pytest.exe` | `.venv/Scripts/mypy.exe` |
| **POSIX (Bash / Linux / macOS)** | `source .venv/bin/activate` | `.venv/bin/python` | `.venv/bin/pytest` | `.venv/bin/mypy` |

*Note: For package running, prefer using `uv run <command>` if available.*

### Git Workspace Checks
- `git status` to verify a clean working tree before and after changes.
- `Get-Content README.md` (Windows) or `cat README.md` (POSIX) to review the current repo contract.
- `Get-Content PLAN.md` (Windows) or `cat PLAN.md` (POSIX) to confirm architecture and milestone assumptions.

Planned local tooling in `PLAN.md` is Python 3.11+, `uv` or `poetry`, Node.js 20+, `gcloud`, and Docker. Align new automation with that stack instead of introducing parallel tooling.

## Coding Style & Naming Conventions
Prefer Python-first conventions because the planned runtime is ADK + data-science tooling. Use 4-space indentation, `snake_case` for modules and functions, `PascalCase` for classes, and short, descriptive file names. Keep agent boundaries explicit in names such as `research_agent.py` or `sentinel_policy.py`. Favor small modules over monolithic notebooks or scripts.

## Dashboard & Front-End Design System
To maintain visual consistency and prevent regression, any modification or addition to the frontend dashboard (`src/dashboard/`) must strictly adhere to the retro-brutalist Terminal CLI guidelines defined in [DESIGN.md](file:///C:/Users/henju/Projects/sentinelds/DESIGN.md). Always consult [DESIGN.md](file:///C:/Users/henju/Projects/sentinelds/DESIGN.md) before editing frontend styles, assets, or interactive layouts.

## Testing Guidelines
Add tests alongside new code rather than deferring them. Use `tests/` with file names like `test_research_agent.py`. Cover agent orchestration, Sentinel pre-flight decisions, and telemetry emission paths first. If you add a test runner, standardize on one command and document it in `README.md`.

## Commit & Pull Request Guidelines
All git commits must be handled and executed exclusively by the user; agents must stage files but never execute `git commit` or push commands directly. Recent history uses short, imperative messages such as `Update README repo layout` and `updated PLAN.md`. Keep commits focused and readable; mention the file or subsystem when useful. PRs should include a concise summary, linked issue or milestone, test evidence, and screenshots or trace captures for dashboard, telemetry, or demo-flow changes. Always refer to `.github/pull_request_template.md` when creating a pull request.

## Security & Configuration Tips
Do not commit `.env` files, service-account keys, OTLP tokens, MCP credentials, datasets, or model artifacts. Follow `.gitignore` for local outputs, and keep any security-sensitive demo setup documented in `PLAN.md` or `README.md` rather than hardcoded in source.
