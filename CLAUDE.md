# Project Guide

## What this repo is
Three concerns share this repo:
1. **AWS COG conversion** (primary): convert GeoTIFFs → Cloud-Optimized GeoTIFFs, fix
   nodata, reproject, upload to S3. Code in `lib/` (core / analysis / processors), top-level
   scripts (`update_nodata_cog.py`, `convert_nodata_to_zero.py`, `check_nodata.py`), and
   notebooks in `templates/`. GDAL/rasterio based.
2. **LOE/FTE capacity-report POC**: a GitHub Action that reads team **Objective** issues +
   a **Projects v2** board and reports staffing capacity per Program Increment. Code in
   `loe-poc/`, `.github/scripts/generate_loe_report.py`, `.github/workflows/loe-report.yml`.
   Full detail in `docs/LOE_POC.md`.
3. **LOE capacity dashboard**: a static Vite+React SPA in `loe-dashboard/` that visualizes
   the LOE reports and adds in-browser what-if editing. Deployed on Netlify from `main`
   (`netlify.toml` at repo root). Detail in `loe-dashboard/README.md`.

## LOE POC — critical, non-obvious constraints
- **Data split:** PI and each objective's **Start/End dates come from the project board**
  (fields), **not** the issue body. The **LOE/FTE table lives in the issue body**. The report
  joins them.
- **Board is read, not issues:** the Action calls `gh project item-list` (board → issue),
  never the issue's Projects sidebar.
- **POC board is a personal project** (`kyle-lesinger/projects/1`). Consequence: org-repo
  issues **do not display** it in their "Projects" sidebar (user-project ↔ org-repo-issue is
  one-directional in the UI). The membership is real — verify with `gh project item-list`,
  not the issue page.
- **CI token:** the Action needs repo secret **`PROJECT_TOKEN`** = a **classic** PAT with
  **`repo` + `read:org` + `project`**. The default `GITHUB_TOKEN` cannot read Projects v2.
  `unknown owner type` from `gh project` ⇒ the token is missing `read:org`.
- **`main` is protected** (PRs required). The Action does **not** push reports to `main`; it
  publishes each run to a **per-PI branch `loe-report/<pi>`** (commits accumulate; open a PR
  to keep a snapshot). Pushing reports to main fails with `GH006`.
- **Iteration fields aren't API-creatable**, so the POC board models **Program Increment as a
  single-select** (`PI 26.4`, `PI 27.2`); the parser also handles the real org board's
  **iteration** PI field. Single-select PI windows come from `PI_WINDOWS` in the parser.
- **`.gitignore` globally ignores `*.csv` / `*.json`** — the negations `!reports/*.csv` and
  `!loe-poc/*.json` keep report + tracking files tracked. `git add reports` (local and in CI)
  depends on these.
- **No Jules integration yet.** The report is deterministic (seeded generator + stable
  ordering) specifically as the hook point for future Jules run-diffing.

## Run / test (LOE)
- Offline (no network): `python loe-poc/generate_sample_issues.py && python
  .github/scripts/generate_loe_report.py --issues-json loe-poc/sample_issues.json
  --out-dir reports --now "$(date -u +%FT%TZ)"`
- Against the board: `gh project item-list 1 --owner kyle-lesinger --format json --limit 800
  > items.json && python .github/scripts/generate_loe_report.py --project-json items.json
  --pi "PI 26.4" --out-dir reports --now "$(date -u +%FT%TZ)"`
- Manual Action: **Actions → LOE Capacity Report → Run workflow →** pick PI
  (All / PI 26.4 / PI 27.2) → report lands on `loe-report/<pi>`.

## Demo data + cleanup
50 demo issues **#10–#59** (labels `Objective`, `poc-loe`) tracked in
`loe-poc/created_issues.json`; board item ids in `loe-poc/project_items.json`. Cleanup:
`python loe-poc/cleanup_issues.py --delete` then `gh project delete 1 --owner kyle-lesinger`.

## Capacity rules / roles
Roles are a fixed set: PM, Frontend, Backend, Geospatial, Data Curator, Comms, ML, Designer,
Jupyterhub (other roles / non-numeric FTE → row skipped + warned). Raw FTE summed per person
**per PI** > 1.0 = **over-allocated**; **weighted FTE** = fte × (objective days in PI / PI
days) for partial-window objectives (informational; the flag uses the raw sum).

## LOE Dashboard (`loe-dashboard/`, Netlify) — non-obvious facts
- **Reads data at runtime** from the **public** `loe-report/all-pis` branch raw URLs
  (`src/data.ts`); falls back to the snapshot in `loe-dashboard/public/data/`. **No backend,
  no secrets, no change to the Action** — new reports appear on next page load, no redeploy.
- **Unedited rows reuse the generator's per-row `weighted_fte`** (`weightedOf` in
  `src/compute.ts`). The CSV's `pi_fraction` is only 2-dp rounded, but the generator computed
  weighted from the full-precision fraction, so recomputing `fte × pi_fraction` drifts ±0.01.
  Reusing the CSV value keeps the `✓ matches baseline` self-check exact; only **edited** rows
  recompute (same over-allocation rule: raw Σ FTE > 1.0).
- **What-if edits are browser-only** — never written back to GitHub. Export downloads CSVs.
- **Netlify**: base `loe-dashboard`, publish `dist` (`netlify.toml`). Two one-time steps:
  connect the site to the repo on `main`; run the Action once with `pi = "All PIs"` to seed
  `loe-report/all-pis` (until then the site uses the bundled snapshot).
- **Build**: `cd loe-dashboard && npm ci && npm run build` (`build` is `vite build`, no
  type-check gate; run `npm run typecheck` separately). Dev: `npm run dev`.
