# LOE / FTE Capacity Report — POC

Report team staffing capacity from GitHub **Objective** issues + a **Projects v2** board.
FTE is summed per person **per Program Increment (PI)**; > 1.0 = over-allocated. A duration
**weighted FTE** adjusts for objectives that cover only part of a PI.

## Data model
- **Issue body** holds the `## LOE/FTE` markdown table: `| Person | Role | FTE | Notes |`.
  Roles are a fixed set (PM, Frontend, Backend, Geospatial, Data Curator, Comms, ML, Designer,
  Jupyterhub). Rows with any other role or non-numeric FTE are skipped and warned.
- **Project board fields** hold **Program Increment** (which PI) and **Start Date / End Date**
  (the objective's own window inside the PI). These are deliberately **not** in the issue body.
- **PI window**: on the real org board (`Disasters-Learning-Portal` project **#5**) PI is an
  **iteration** field (window = `startDate` + `duration`). On the POC board it is a
  **single-select**, so the window is looked up from `PI_WINDOWS` in the parser. The parser
  normalizes both shapes.

## Components
| File | Role |
| --- | --- |
| `.github/scripts/generate_loe_report.py` | Parser + report generator (stdlib only). Inputs: `--project-json` (board), `--issues-json` (offline sample), `--from-dir` (md fixtures). `--pi "PI 26.4"` filter. Writes `reports/loe_allocations.csv`, `loe_by_person.csv`, `loe_by_role.csv`, `loe_summary.md`. |
| `.github/workflows/loe-report.yml` | The Action. `workflow_dispatch` PI dropdown; reads board via `gh project item-list`; publishes report to `loe-report/<pi>` branch; run summary + artifact. |
| `.github/ISSUE_TEMPLATE/objective.md` | Objective issue template (LOE table only; a note says PI/dates go on the board). |
| `loe-poc/generate_sample_issues.py` | Seeded generator → `loe-poc/sample_issues.json` (issue body + a `project` block with PI/dates). |
| `loe-poc/create_issues.py` | Opens the demo issues via `gh`; records `loe-poc/created_issues.json`. |
| `loe-poc/setup_project.py` | Adds issues to the board + sets PI/Start/End fields. Resumable/idempotent (reuses existing board items; retries transient errors); records `loe-poc/project_items.json`. |
| `loe-poc/cleanup_issues.py` | Closes/deletes the demo issues (by tracking file or `poc-loe` label). |

## Data flow (the Action)
1. `gh project item-list <n> --owner <owner> --format json` → all board items.
2. Keep items whose issue **title contains "objective"**.
3. Per item: PI + window (iteration, or single-select + `PI_WINDOWS` lookup), objective
   Start/End (board date fields), and the LOE table (issue body).
4. Aggregate per `(PI, person)` and `(PI, role)`; compute raw + weighted FTE.
5. Emit CSVs + `loe_summary.md` (with clickable `[#N](url)` ticket links).
6. Commit to `loe-report/<pi>`, upload artifact, append summary to the run.

**Reconciliation invariant** (tested): Σ allocation FTE == Σ by_person == Σ by_role, per PI,
for both raw and weighted (weighted is rounded per-allocation so it reconciles to the cent).

## Current deployment state
- POC board: **`kyle-lesinger/projects/1`** (id `PVT_kwHOC5zXJc4Bd9S1`). Fields: **Program
  Increment** (single-select: `PI 26.4`, `PI 27.2`), **Start Date**, **End Date** (DATE).
- Demo issues **#10–#59** in `Disasters-Learning-Portal/disasters-aws-conversion`, labels
  `Objective` + `poc-loe`. (Objective numbers 1–50 map to issues 10–59 in creation order.)
- Repo secret **`PROJECT_TOKEN`** set (classic PAT `repo` + `read:org` + `project`).
- Reports publish to **`loe-report/<pi>`** branches (e.g. `loe-report/PI-26.4`,
  `loe-report/PI-27.2`, `loe-report/all-pis`). `main` is never written by the Action.

## Gotchas (with rationale)
- **Personal POC board ⇒ "No projects" on issues.** GitHub does not surface user-owned
  project membership in an org-repo issue's sidebar. Chosen deliberately to avoid polluting
  the live org board (#5 has ~298 real items). To make the sidebar show it, use an org board.
- **`unknown owner type`** from `gh project` = token missing `read:org`.
- **`GITHUB_TOKEN` can't read Projects v2** → the Action must use `PROJECT_TOKEN`.
- **`main` protected** → reports go to per-PI branches, not main (`GH006` otherwise).
- **Iteration fields aren't API-creatable** → POC PI is single-select; parser handles both.
- **`.gitignore` ignores `*.csv`/`*.json`** → negations `!reports/*.csv` / `!loe-poc/*.json`
  are load-bearing for committing reports.

## Run / cleanup
```bash
# offline
python loe-poc/generate_sample_issues.py
python .github/scripts/generate_loe_report.py --issues-json loe-poc/sample_issues.json \
  --out-dir reports --now "$(date -u +%FT%TZ)"

# against the board
gh project item-list 1 --owner kyle-lesinger --format json --limit 800 > items.json
python .github/scripts/generate_loe_report.py --project-json items.json --pi "PI 26.4" \
  --out-dir reports --now "$(date -u +%FT%TZ)"

# full demo from scratch
gh label create Objective --color 1d76db --force
gh label create poc-loe   --color 5319e7 --force
python loe-poc/create_issues.py
python loe-poc/setup_project.py

# cleanup
python loe-poc/cleanup_issues.py --delete
gh project delete 1 --owner kyle-lesinger
```

## Future
- **Jules** (not built): the report is deterministic on purpose. A future job would diff
  `loe-report/<pi>` across runs to flag new over-allocations, FTE drift, added/removed
  objectives.
- **Org board**: point `POC_PROJECT_OWNER` / `POC_PROJECT_NUMBER` (workflow) and
  `loe-poc/setup_project.py` at the org board (**#5**, owner `Disasters-Learning-Portal`) so
  issues show the project in their sidebar. #5's PI is an iteration field (already supported).
