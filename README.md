# Codexpp

> Languages: [English](https://github.com/avometre/Codexpp/blob/main/README.md) · [Türkçe](https://github.com/avometre/Codexpp/blob/main/README.tr.md)

[![PyPI](https://img.shields.io/pypi/v/codexpp)](https://pypi.org/project/codexpp/)
[![Python](https://img.shields.io/pypi/pyversions/codexpp)](https://pypi.org/project/codexpp/)
[![License](https://img.shields.io/pypi/l/codexpp)](LICENSE)
[![CI](https://github.com/avometre/Codexpp/actions/workflows/ci.yml/badge.svg)](https://github.com/avometre/Codexpp/actions/workflows/ci.yml)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/avometre/Codexpp?quickstart=1)

Codexpp is an extension framework that turns the OpenAI Codex CLI into a structured, persona-driven workflow engine built for repeatable delivery. It delivers reusable slash commands, persona-driven guidance, and automatic MCP (Model Context Protocol) setup to make Codex sessions more productive and consistent.

## Table of Contents
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Codex CLI Utilities](#codex-cli-utilities)
- [Prompt Authoring](#prompt-authoring)
- [Command Details](#command-details)
- [Parameter Glossary](#parameter-glossary)
- [Contributing](#contributing)
- [License](#license)

## Features
- **Slash Commands:** TOML-based definitions surface as `cx:*` commands inside Codex CLI.
- **Persona Mode:** Apply roles such as `system-architect`, `implementation-engineer`, or `code-reviewer` with a single flag.
- **Automatic Integration:** `codexpp codex install` wires commands, prompt files, and MCP profiles into Codex CLI.
- **Prompt Templates:** Markdown-based prompts (YAML front matter + sectioned output) power every `cx:*` command and are auto-synchronized into Codex CLI.
- **Template Validation:** Prompt placeholders are validated before execution to prevent missing variables, ensuring Codex never runs with missing inputs.
- **Persona Synchronisation:** Keep project and global `AGENTS.md` files up-to-date with one command.
- **MCP Management:** Ships with popular MCP servers (Filesystem, Context7, GitHub, Memory, Sequential Thinking, Puppeteer).

## Installation

### Requirements
- Python 3.11+
- Node.js & npm (for Codex CLI)
- Codex CLI (`npm install -g @openai/codex`)

### From PyPI

Recommended (isolated CLI):
```bash
pipx install codexpp
# or
uv tool install codexpp
```

Alternatives:
```bash
# Use a project virtualenv (venv)
python -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install codexpp

# or use a project virtualenv with UV
uv venv .venv && source .venv/bin/activate
uv pip install codexpp
```

### Development setup
```bash
git clone https://github.com/avometre/codexpp.git
cd codexpp
uv venv .venv && source .venv/bin/activate
uv pip install -e .
```
(You can swap UV for `python -m venv` + `pip install -e .` if you prefer.)

Verify the installation:
```bash
codexpp --help
codexpp codex status
```

## Quick Start
Use the following flow to enable `cx:*` commands inside Codex CLI:

1. **Install commands into Codex CLI**
   ```bash
   codexpp codex install --force
   ```
   - Updates the slash command block in `~/.codex/config.toml`.
   - Writes prompt templates into `~/.codex/prompts/`.
   - Installs the bundled prompt templates and MCP profiles, so no extra tools or manual copying is required.

2. **Launch Codex CLI**
   ```bash
   codex
   ```
   In the `/prompts:` menu you will see `cx:analyze`, `cx:implement`, `cx:review`, and the rest of the commands ready to run.

3. **One-shot project setup**
   ```bash
   codexpp codex init --profile full --force
   ```
   Creates bootstrap folders, synchronises personas, installs command packs, and wires everything into Codex CLI in a single step.

## Codex CLI Utilities

### `codexpp codex install`
Installs the bundled slash commands and MCP profiles into your local Codex CLI configuration. Use the safety-related flags below when running on a shared machine or when you want to preview the changes first.

**Useful flags**
- `--dry-run` — print the planned config diff and MCP summary without touching any files or syncing prompts.
- `--backup` — write a `<config>.bak` snapshot before modifying `~/.codex/config.toml`.
- `--backup-path PATH` — send the backup to a custom location (e.g. version-controlled dotfiles repo).
- Automatically searches for the Codex CLI in common npm/pnpm install directories (falls back to `--codex-bin` if you need a custom path).

Example dry-run output:

```bash
$ codexpp codex install --dry-run
[codexpp] [1/5] Preparing Codex CLI context
    • Project path : /workspace/codexpp
    • Codex binary : /usr/local/bin/codex
[codexpp] [2/5] Loading command definitions
    • Base commands : 12
    • Command packs : (none)
    • Total commands: 12
...
[codexpp] [5/5] Syncing Codex prompt templates
    • Target directory: /home/me/.codex/prompts
    • Force overwrite : False
[codexpp] Codex install completed.
```

### `codexpp codex uninstall`
Cleans the slash command block, prompt templates, and MCP profiles that were previously installed.

**Useful flags**
- `--dry-run` — list the config diff and every prompt/MCP file that would be removed.
- `--backup` / `--backup-path PATH` — same backup behaviour as `codex install`.
- `--prompts-dir` / `--mcp-dir` — override the target directories if your Codex CLI lives elsewhere.

Dry-run example:

```bash
$ codexpp codex uninstall --dry-run
[codexpp] [1/4] Analyzing Codex installation
    • Config path : /home/me/.codex/config.toml
    • Prompts dir : /home/me/.codex/prompts (12 file(s) tracked)
    • MCP dir     : /home/me/.codex/mcp (6 file(s) tracked)
[codexpp] Dry run enabled; no files were changed.
```

### `codexpp version`
Shows detailed environment info without touching your Codex setup.

**Highlights**
- Prints the codexpp package version, install path, Python executable, and Codex CLI binary/version.
- Use `--json` for machine-readable output or `--codex-bin` to probe a custom Codex CLI path.

```bash
$ codexpp version
Codexpp 0.x.y
  Location : /workspace/codexpp/codexpp
  Python   : 3.11.9 (/usr/local/bin/python3)
  Codex CLI: /usr/local/bin/codex — codex 0.56.0
```

## Prompt Authoring

Every `cx:*` command ships with a Markdown template located under `codexpp/resources/prompts/default/`.
Each file follows the same structure:

```markdown
---
title: Repository Analysis
description: Analyze the selected scope and provide an evidence-based briefing.
argument_hint: TARGET=<path> [CONTEXT="notes"] [FOCUS="areas"] [DEPTH=medium]
persona: system-architect
---

...section headings and bullet guidance that reference $TARGET/$FOCUS/etc...
```

Key points:
- The YAML front matter defines metadata plus `argument_hint` and `persona`.
- Inside the body, `$PLACEHOLDER` tokens (e.g., `$TARGET`, `$FOCUS`) are for readability and guidance in the Codex CLI prompts. When using `codexpp commands run`, parameters are rendered as `{{target}}`-style variables from the TOML definitions; the synced Codex prompts keep the `$PLACEHOLDER` text as-is.
- When you run `codexpp commands render` or `codexpp codex install`, the CLI syncs these Markdown templates as-is (including front matter) into Codex.

To customize or add prompts:
1. Edit/create the Markdown file under `codexpp/resources/prompts/default/`.
2. (Optionally) update `codexpp/resources/commands/*.toml` if you need new inputs or metadata.
3. Run `codexpp commands render <id>` to preview, or `codexpp codex install --force` to push into Codex CLI.

## Command Details

- `cx:analyze`
  - Purpose: Evidence-based repository analysis for a selected scope; no implementation code.
  - Persona: `system-architect`
  - Output: Executive Summary; Architecture & Data Flow; Dependencies & Surfaces; Quality & Risk; Hotspots & Evidence; Recommendations & Roadmap
  - Usage hint: `TARGET=<path or scope> [CONTEXT="..."] [FOCUS="..."] [DEPTH=light|medium|deep]`

- `cx:implement`
  - Purpose: Plan and describe concrete code and test changes in small, verifiable steps.
  - Persona: `implementation-engineer`
  - Output: Implementation Summary; Plan & Steps; Code Changes By Area; Tests; Manual Verification; File Summary
  - Usage hint: `SPEC="<feature or task>" [NOTES="..."] [FLAG="..."]`

- `cx:review`
  - Purpose: Senior-level code review with prioritized, actionable feedback.
  - Persona: `code-reviewer`
  - Output: Change Summary; Review Classification; Strengths; Issues – Must Fix; Issues – Should Fix; Issues – Nice To Have; Tests And Coverage; Overall Recommendation
  - Usage hint: `DIFF_SOURCE=<diff or ref> [FOCUS="..."] [RISK=low|medium|high]`

- `cx:plan`
  - Purpose: Turn a feature/problem into a staged implementation plan with risks and tests.
  - Persona: `system-architect`
  - Output: Overview; Assumptions; High-Level Approach; Step-By-Step Plan; Testing Strategy; Risks And Trade-Offs; Dependencies And Sequencing
  - Usage hint: `SPEC="<feature or problem>" [HINTS="..."] [CONSTRAINTS="..."] [ESTIMATE=true|false]`

- `cx:test`
  - Purpose: Practical test strategy (behaviors, scenarios, cases, commands).
  - Persona: `implementation-engineer`
  - Output: Test Goal; Existing Coverage; Test Scenarios; Test Cases; Test Implementation Plan; Edge Cases And Risks; Next Actions
  - Usage hint: `CHANGE="<summary>" [TESTS="..."] [COVERAGE="percent or notes"]`

- `cx:doc`
  - Purpose: Audience-tailored documentation for a change.
  - Persona: `system-architect`
  - Output: Overview; Audience And Impact; Key Concepts And Behavior; How To Use / Integrate; Operational Notes; Follow-Up Documentation
  - Usage hint: `CHANGE="<summary>" [AUDIENCE="developer|user|API|ops"] [STYLE="..."]`

- `cx:deploy`
  - Purpose: Safe, repeatable deployment plan with pre-checks, steps, verification, and rollback readiness.
  - Persona: `implementation-engineer`
  - Output: Deployment Summary; Pre-Deployment Checks; Deployment Steps; Verification & Observability; Rollback Readiness; Next Actions
  - Usage hint: `NOTES="<release notes>" ENVIRONMENT=<env> [WINDOW="..."] [FLAG="..."]`

- `cx:rollback`
  - Purpose: Fast, safe rollback plan with triggers, steps, and follow-ups.
  - Persona: `implementation-engineer`
  - Output: Rollback Summary; Rollback Scope; Preconditions And Safety Checks; Rollback Steps; Post-Rollback Verification; Risks And Irreversible Effects; Follow-Up Actions
  - Usage hint: `INCIDENT="<summary>" [VERSION="<current or target>"] [DB_IMPACT=yes|no] [FEATURE_FLAG="..."]`

- `cx:status`
  - Purpose: Operational status briefing summarizing health, incidents, risks, and actions.
  - Persona: `system-architect`
  - Output: Status Summary; Status Classification; What Is Healthy; What Is Concerning; Incidents & Outstanding Work; Recommendations
  - Usage hint: `SCOPE="<service or module>" [METRICS="..."] [SLO="..."]`

- `cx:security`
  - Purpose: Focused security audit with prioritized findings and concrete mitigations.
  - Persona: `code-reviewer`
  - Output: Security Overview; Assets And Threat Model; Key Findings; Severity Breakdown; Recommended Fixes; Testing And Validation; Next Actions
  - Usage hint: `TARGET=<scope> [CONTEXT="..."] [FOCUS="..."] [DEPTH=light|medium|deep] [FORMAT=markdown|json|yaml|html]`

## Parameter Glossary

- `TARGET` — Directory, package, or file scope. Defaults to current directory (`.`). Examples: `src/`, `pkg/payments`, `src/app.py`.
- `CONTEXT` — Free-form notes or constraints to shape answers (e.g., "monolith", "internal only", "performance first").
- `FOCUS` — Comma-separated focus tags; not strict, they guide the output. Common values: `arch,deps,tests,perf,security,readability`.
  - Examples: `FOCUS=arch,tests`, `FOCUS=security,perf`.
- `DEPTH` — How exhaustive the analysis/audit is: `light` (high-level), `medium` (balanced), `deep` (thorough, more hotspots and specifics).
- `FORMAT` — Output format for `cx:security`: `markdown` (default), `json`, `yaml`, `html`.
- `RISK` — Expected risk level for `cx:review`: `low|medium|high`; influences strictness/priorities in review.
- `ESTIMATE` — Whether `cx:plan` includes rough time estimates: `true|false` (default `false`).
- `COVERAGE` — Coverage target for `cx:test`. Number or percent string (e.g., `80` or `80%`).
- `FLAG` — Feature flag name used to guard rollouts in `cx:implement`/`cx:deploy`.
- `WINDOW` — Maintenance window text used by `cx:deploy` (e.g., `2025-11-14 03:00–04:00 UTC`).
- `SCOPE` — Service or module name for `cx:status` (e.g., `payments-api`).
- `METRICS` — Highlighted metrics or dashboard links for `cx:status`.
- `SLO` — SLO targets for `cx:status` (e.g., `99.9% monthly availability`).
- `HINTS` — Repo hints for `cx:plan` (e.g., `src/users, tests/test_users.py`).
- `CONSTRAINTS` — Assumptions/limits for `cx:plan` (e.g., `no DB migrations`).
- `ENVIRONMENT` — Target environment for `cx:deploy` (e.g., `staging`, `production`).
- `INCIDENT` — Incident summary or link for `cx:rollback`.
- `VERSION` — Current or rollback target version for `cx:rollback` (e.g., `v1.2.3`).
- `DB_IMPACT` — `yes|no` indicator for data/migration impact in `cx:rollback`.
- `FEATURE_FLAG` — Flag to disable during `cx:rollback`.

Passing parameters examples:
- Inside Codex CLI: follow each command’s `argument_hint` shown in the `/prompts` menu.
- From shell with codexpp: `codexpp commands run cx:analyze --set target=src/ --summary`.

## Contributing

Contributions are welcome via issues and pull requests. Please keep changes small and focused, follow the existing style, and include tests or updates to documentation when relevant.

## License

MIT License — see `LICENSE` for details.
