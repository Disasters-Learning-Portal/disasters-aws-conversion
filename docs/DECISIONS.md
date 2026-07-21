# Architectural Decisions

Short decision records. Newest first. Scope: LOE/FTE capacity-report POC + dashboard.

## ADR-11: Report Action auto-opens a living PR to main, linking the live dashboard
The Action opens (once) a PR from `loe-report/<pi>` → `main` after each run (workflow step 11,
`gh pr create`/`pr list`, `pull-requests: write`); later runs reuse it. The PR **body links to
the live dashboard** (`DASHBOARD_URL` = the Netlify production URL). We deliberately do NOT rely
on the per-PR Netlify **Deploy Preview**: the dashboard fetches `loe-report/all-pis` data at
runtime, so the production URL renders identical data, and every run rewrites the report's
timestamp → a new commit, so rapid runs make Netlify **auto-cancel** the superseded preview
builds (the `deploy-preview-<N>` URL 404s). One living PR per PI; not auto-merged (merge to
snapshot into main). Supersedes the "open a PR manually" note in ADR-3.

## ADR-10: Dashboard reuses the generator's per-row weighted FTE (no recompute for unedited rows)
`loe_allocations.csv` stores `pi_fraction` rounded to 2 dp, but the generator computed each
row's `weighted_fte` from the **full-precision** fraction. Recomputing `fte × pi_fraction` in
the browser drifts ±0.01 vs the report (and Python's `round()` is banker's, not half-up). So
the dashboard reuses each row's `weighted_fte` from the CSV verbatim for unedited rows and
only recomputes rows the user edits (what-if). Keeps the `✓ matches baseline` self-check exact
(0 mismatches across all 50 aggregate rows). See `loe-dashboard/src/compute.ts` (`weightedOf`).

## ADR-9: Capacity dashboard is a static SPA that reads reports at runtime (no workflow coupling)
The repo is public, so the dashboard (`loe-dashboard/`, Vite+React, Netlify) fetches the LOE
CSVs directly from the public `loe-report/all-pis` branch raw URLs at page load, with a
bundled snapshot fallback. Rejected: having the Action build/deploy the site or bundle data
per run. Runtime fetch means **no secrets, no Action changes, no redeploy** when reports
refresh. What-if edits stay client-side (never written to GitHub). Cost: ~5-min raw-CDN cache
and a heavier client bundle (Recharts) — both fine for an internal tool.

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
