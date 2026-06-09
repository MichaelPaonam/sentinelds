---
name: sentinelds_preflight
description: Guides the pre-flight check sequence for SentinelDS development, enforcing the Windows .venv python rule, dependency lock verification (preventing wrong command execution), and Sentinel pre-flight authorization.
---

# SentinelDS Pre-Flight Operational Guidelines

Use this skill whenever setting up, building, testing, linting, or running Python-related tasks for the SentinelDS project.

## 1. The Local `.venv` Rule
* Always run Python tools via the local virtual environment located in the workspace:
  - **Windows (PowerShell/CMD)**:
    - Python Interpreter: `.venv/Scripts/python.exe`
    - Package Runner: `uv run` or `.venv/Scripts/pip.exe`
    - Type Checker (`mypy`): `.venv/Scripts/mypy.exe`
    - Test Runner (`pytest`): `.venv/Scripts/pytest.exe`
  - **POSIX (Linux/macOS Bash)**:
    - Python Interpreter: `.venv/bin/python`
    - Package Runner: `uv run` or `.venv/bin/pip`
    - Type Checker (`mypy`): `.venv/bin/mypy`
    - Test Runner (`pytest`): `.venv/bin/pytest`
* Never run raw global `python` or `pip` commands, as this causes environment mismatches.

## 2. Dependency & Lock Verification
* Before calling any linting or development utility (e.g. `ruff`), inspect `pyproject.toml` and `uv.lock` to ensure the tool is actually installed in the workspace.
* **The Ruff Restriction**: Configuration sections for `ruff` exist in `pyproject.toml`, but `ruff` is **NOT** listed in the dependencies or lock file. Do not run any `ruff` commands. Run static typing checks via `.venv\Scripts\mypy` instead.

## 3. Sentinel Pre-Flight Security Authorization
* Risky tools (including training executors, web/network fetches, or file writes) are bound by the Sentinel pre-flight defense loop.
* Before implementing or running these operations, ensure the Sentinel pre-flight decorator (`@sentinel_guard("tool_name")`) or explicit verdict checking is integrated:
  - If the Dynatrace MCP or Sentinel Agent returns `Verdict.HALT`, raise a `PermissionError` and halt immediately.
  - If the MCP server is unreachable, the execution must **fail-closed** for risky tools, preventing unchecked execution.
