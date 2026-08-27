# Editor Setup

This document covers optional editor tooling for contributors working on `gridworks-scada`.

None of the tools below are required to run the code or contribute changes, but they can improve feedback while developing.

---

## Recommended Editor

Many contributors use VS Code, though any Python-capable editor is fine.

---

## Ruff (Linting Feedback)

The repository includes configuration for  BsCode.

Install Ruff in your editor to get inline warnings and style feedback while editing.

From the command line:

    ruff check

Notes:

- Ruff is currently advisory.
- The full repository may not yet pass all configured checks.
- Use it as helpful feedback, not as a blocker.

---

## VS Code + Ruff Extension

If using VS Code:

1. Install the Ruff extension.
2. Enable it for this workspace if desired.
3. Use Problems / Diagnostics panes for live feedback.

---

## Python Type Checking

Basic type checking can be useful for catching mistakes early.

If using :contentReference[oaicite:3]{index=3} with Pylance:

1. Open Settings
2. Search for `python.analysis.typeCheckingMode`

Suggested settings:

- `basic` — good default
- `strict` — stronger checks, may be noisy in parts of the repo

Because portions of the repository are still evolving, workspace-level or user-level tuning may be helpful.

---

## Recommended Python Interpreter

Use the repo virtual environment created by:

    ./tools/mkenv.sh

Then point your editor at:

    gw_spaceheat/venv/bin/python

This ensures imports and installed dependencies match local development.

---

## Import Resolution

If your editor has trouble resolving local modules, ensure the repository root is opened as the workspace folder and that the virtual environment is selected.

Some contributors also set `PYTHONPATH` when working in shell sessions.

---

## Minimal Setup

If you want the quickest useful setup:

1. Select the repo virtual environment
2. Enable Ruff
3. Use basic type checking

That is enough for most contributors.

---

## Troubleshooting

### Editor shows missing imports

Usually caused by selecting the wrong interpreter. Re-select:

    gw_spaceheat/venv/bin/python

### Too many warnings

Reduce type checking strictness or disable specific extensions temporarily.

### CLI works but editor is confused

The shell environment and editor interpreter are likely different. Align them first.