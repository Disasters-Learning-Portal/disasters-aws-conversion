# Architectural Decisions

Short decision records. Newest first. Scope: LOE/FTE capacity-report POC.

## ADR-8: `.gitignore` negations for report + tracking files
The repo globally ignores `*.csv` and `*.json`. Report CSVs and the demo tracking JSONs must
be committed (and the Action commits `reports/`), so `!reports/*.csv` and `!loe-poc/*.json`
were added. **Load-bearing** — removing them breaks report commits locally and in CI.

## ADR-7: No Jules integration (yet)
Jules is a stated future goal but is **not** wired in. Instead the report is made
**deterministic** (seeded generator, stable ordering, rounded weighted FTE) so a future Jules
job can diff `loe-report/<pi>` across runs. Keep output deterministic.

## ADR-6: Over-allocation flagged on the raw per-PI FTE sum
User rule: "sum the FTE… not more than 1 per PI." Flag = raw Σ FTE per person per PI > 1.0.
**Weighted FTE** (fte × fraction of PI covered) is reported alongside as the time-averaged
view but does **not** drive the flag.

## ADR-5: PI naming left as `PI 27.2` (not renamed to 27.1)
The real board's next iteration is literally `PI 27.2`. A rename to `27.1` was considered and
explicitly declined by the user ("too much work"). POC board + parser + workflow all use
`PI 26.4` and `PI 27.2`.

## ADR-4: `PROJECT_TOKEN` (classic PAT) for CI
The default `GITHUB_TOKEN` cannot read org/user Projects v2 boards. The Action reads the board
with a repo secret `PROJECT_TOKEN` = classic PAT with `repo` + `read:org` + `project`.
`read:org` is required or `gh project` fails with `unknown owner type`.

## ADR-3: Reports publish to per-PI branches, not `main`
`main` is protected (PRs required), so the Action's `git push` of the report was rejected
(`GH006`). Each run now commits the report to `loe-report/<pi>` (commits accumulate); open a
PR to `main` to keep a snapshot. This also keeps report churn out of main history.

## ADR-2: Program Increment modeled as single-select on the POC board
Projects v2 **iteration** fields cannot be created via the API (`gh project field-create`
supports only TEXT/SINGLE_SELECT/DATE/NUMBER). The POC board uses a single-select PI; the
parser normalizes both single-select (window via `PI_WINDOWS`) and iteration (window intrinsic)
so it works against the POC board now and the real org board later.

## ADR-1: Separate throwaway POC project, not the live org board
The real Disasters Learning Portal board (**#5**) has ~298 live items across org repos. To
avoid polluting it, the POC uses a personal throwaway board (`kyle-lesinger/projects/1`).
**Consequence:** org-repo issues do not show a user-owned project in their sidebar, so the 50
demo issues display "No projects" even though they are on the board. Switch to an org board to
change that.
