# LOE / FTE Capacity Report — POC

Proof of concept for tracking team workload from **Objective** GitHub issues, where
staffing (LOE/FTE) lives in the **issue body** and the **Program Increment (PI)** and
each objective's **Start/End dates** live on the **project board**.

A GitHub Action reads the board, joins the two, sums FTE **per person per PI**, and
commits a capacity report to [`reports/`](../reports/).

## Core concepts

- **PI (Program Increment):** the ~3-month objective window, a **project field**. On the
  real *Disasters Learning Portal* board it is an **iteration** field (the window travels
  with the value, e.g. PI 26.4 = 2026-07-12 → 2026-10-17). Iteration fields aren't API-
  creatable, so the **throwaway POC board** models PI as a **single-select** (`PI 26.4`,
  `PI 27.2`) and the report maps the PI to its window. The parser handles **both**.
- **Objective window:** project **Start Date / End Date** date fields. If an objective covers
  only part of its PI, the report adds a **weighted FTE** = `fte × (days in PI / PI days)`.
- **FTE / capacity rule:** raw FTE summed per person **per PI** must not exceed 1.0; anyone
  over is flagged **over-allocated** (flag is on the raw sum; weighted is informational).
- **Roles (fixed set):** PM, Frontend, Backend, Geospatial, Data Curator, Comms, ML,
  Designer, Jupyterhub. Rows with any other role (or non-numeric FTE) are skipped + warned.

## Files

| Path | Purpose |
| --- | --- |
| [`.github/ISSUE_TEMPLATE/objective.md`](../.github/ISSUE_TEMPLATE/objective.md) | Objective template (LOE table; PI/dates set on the board) |
| [`.github/scripts/generate_loe_report.py`](../.github/scripts/generate_loe_report.py) | Parser + report generator (stdlib only) |
| [`.github/workflows/loe-report.yml`](../.github/workflows/loe-report.yml) | The Action (descriptive per-phase steps; `pi` input) |
| [`generate_sample_issues.py`](generate_sample_issues.py) | Seeded generator for 50 varied demo tickets |
| [`create_issues.py`](create_issues.py) | Opens the demo tickets as real GitHub issues |
| [`setup_project.py`](setup_project.py) | Adds issues to the POC board + sets PI/Start/End fields |
| [`cleanup_issues.py`](cleanup_issues.py) | Closes/deletes the demo issues (tracked for removal) |
| [`sample_issues.json`](sample_issues.json) | Generated tickets (body + `project` block); offline fixture |
| [`created_issues.json`](created_issues.json) | The 50 real issues created (for cleanup) |
| [`project_items.json`](project_items.json) | Board item IDs + PI/dates set per issue |

## POC board

Throwaway Projects v2 board **[LOE Capacity POC](https://github.com/users/kyle-lesinger/projects/1)**
(owner `kyle-lesinger`, #1) with fields: **Program Increment** (single-select), **Start Date**,
**End Date** (dates). Separate from the live team board (zero impact).

## Run it

Offline (no network; PI/dates from `sample_issues.json`'s `project` block):
```bash
python loe-poc/generate_sample_issues.py
python .github/scripts/generate_loe_report.py --issues-json loe-poc/sample_issues.json \
  --out-dir reports --now "$(date -u +%FT%TZ)"
```

Against the live POC board (needs `gh` with `project` scope):
```bash
gh project item-list 1 --owner kyle-lesinger --format json --limit 800 > items.json
python .github/scripts/generate_loe_report.py --project-json items.json \
  --pi "PI 26.4" --out-dir reports --now "$(date -u +%FT%TZ)"   # --pi optional
```

Full demo setup from scratch:
```bash
gh label create Objective --color 1d76db --force
gh label create poc-loe   --color 5319e7 --force
python loe-poc/create_issues.py            # create 50 real issues
python loe-poc/setup_project.py            # add to board + set PI/Start/End (resumable)
```

## The GitHub Action

`loe-report.yml` runs the same pipeline in CI, each phase a labeled step
(context → token check → fetch board → filter → generate → publish summary → commit →
artifact). Notable:

- **`workflow_dispatch` `pi` input** — an insertable field to calculate a single PI
  (`--pi`); blank = all PIs.
- **`PROJECT_TOKEN` secret** — the default `GITHUB_TOKEN` can't read a Projects v2 board,
  so the workflow reads it with a classic PAT (scopes `project` + `repo`) stored as the repo
  secret `PROJECT_TOKEN`. Create it once, then the Action runs end-to-end.
- **push** to `poc/loe-report` proves it on the branch; **schedule/issues** activate on `main`.

## Determinism & Jules

The generator is **seeded** and the report uses stable ordering, so runs diff cleanly — the
hook point for **Jules** to analyze discrepancies between workflow runs (new over-allocations,
FTE drift, added/removed objectives).

## Cleanup

```bash
python loe-poc/cleanup_issues.py --delete          # delete the 50 tracked demo issues
gh project delete 1 --owner kyle-lesinger          # delete the throwaway POC board
```
