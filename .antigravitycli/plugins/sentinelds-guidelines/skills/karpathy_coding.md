---
name: karpathy_coding
description: Applies Andrej Karpathy's four development principles (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution) to combat common LLM coding pitfalls, ensuring precise, clean, and senior-grade code changes.
---

# Karpathy-Inspired Coding Guidelines

Use this skill to guide your planning, implementation, and review workflows for any software task.

## 1. Think Before Coding
* **Rule**: Don't assume. Don't hide confusion. Surface tradeoffs.
* **Practice**:
  - Before writing code, state your assumptions explicitly.
  - If multiple interpretations of a task exist, present them to the user instead of picking one silently.
  - If a simpler approach is possible, push back and suggest it.
  - If you encounter confusion or lack of clarity, stop immediately and ask for clarification.

## 2. Simplicity First
* **Rule**: Write the minimum code that solves the problem. Nothing speculative.
* **Practice**:
  - Do not implement features or configurability beyond what is explicitly requested.
  - Avoid creating complex abstractions for single-use or local code.
  - Do not add speculative error handling for scenarios that are impossible or out of scope.
  - If a 200-line solution can be cleanly rewritten in 50 lines, rewrite it.

## 3. Surgical Changes
* **Rule**: Touch only what you must. Clean up only your own mess.
* **Practice**:
  - Strictly match the existing codebase's formatting, indentation, and style.
  - Do not "improve" or refactor adjacent comments, formatting, or working code that is unrelated to the task.
  - If changes create orphaned variables, imports, or functions, remove them immediately.

## 4. Goal-Driven Execution
* **Rule**: Define clear success criteria and loop until verified.
* **Practice**:
  - Translate imperative task descriptions into declarative success criteria (such as writing tests first or defining metric expectations).
  - Draft a brief, verifiable step-by-step plan before execution.
  - Execute testing, linting, and formatting tools in a loop, and do not mark a task complete until all criteria are met.
