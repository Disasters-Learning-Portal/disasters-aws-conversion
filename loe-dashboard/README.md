# LOE / FTE Capacity Dashboard

An interactive dashboard for the LOE (Level of Effort) / FTE capacity reports produced by
the `loe-report` GitHub Action. It turns the generated CSVs into a spreadsheet-style
**capacity matrix**, charts, filterable tables, and an in-browser **what-if editor** so PMs
can visualize over-allocation and model re-balances without touching GitHub.

Static single-page app (Vite + React + TypeScript). No backend, no secrets.

## Two tabs (switch bottom-left)

1. **Capacity Matrix** (default, read-only) — a **people × objectives** pivot. Objective
   columns are grouped into **collapsible Initiative groups** (click the header to fold a
   group into a single `Σ Initiative` subtotal column); a **Project** dropdown scopes the
   view. A person who holds more than one role gets **one row per role**: the **Per role**
   column sums that role and the bold **Per person** column (a merged cell spanning the
   person's role rows) sums all of them. Footer rows give **Total per objective** and **Total
   per initiative**. Each objective header links to its GitHub ticket.
2. **What-if Dashboard** — the original headline cards, per-person / per-role charts, and the
   editable allocations table (below). Reset/Export live in the header on this tab only.

Grouping comes from the `project` / `initiative` / `team` columns in `loe_allocations.csv`
(read from the board by the generator). CSVs written before those columns existed group under
**"Unspecified"** rather than breaking.

## How it gets data

The reports are published by the Action to the **public** branch `loe-report/all-pis` as
`reports/loe_*.csv`. This site fetches those files **at runtime** from
`raw.githubusercontent.com` (with a cache-buster), so it always shows the latest report
**without a redeploy**. If that branch/file is unavailable, it falls back to the snapshot
bundled in [`public/data/`](public/data/). A badge in the header shows which source is live
(`● live` vs `● snapshot`) and the report's generation time.

The `loe_allocations.csv` rows are the source of truth; `loe_by_person.csv` /
`loe_by_role.csv` are the generator's aggregates, used only to validate that the in-browser
recompute reproduces the Python numbers exactly (the `✓ matches baseline` badge).

## Features

- **Headline cards** — objectives, people, over-allocated (person·PI) pairs, total raw &
  weighted FTE. Recompute live as you edit.
- **Capacity by person** — raw vs weighted FTE per person with a dashed **1.0 full-time
  cap**; bars over 1.0 turn red.
- **Capacity by role** — FTE demand per role (staffing signal).
- **Allocations — what-if editor** — filter by person / role / PI / over-allocated, click
  through to the GitHub objective, and edit any FTE to model a re-balance. Person, role and
  headline totals update instantly. **Edits stay in your browser and are never written back
  to GitHub.**
- **Export** — download the (adjusted) allocations, by-person, or by-role CSV. Files are
  suffixed `_whatif` when edits are active.

## Local dev

```bash
cd loe-dashboard
npm install
npm run dev        # http://localhost:5173
npm run build      # -> dist/
npm run typecheck  # tsc --noEmit
```

## Deploy on Netlify (one-time)

Build config lives in [`../netlify.toml`](../netlify.toml) (base `loe-dashboard`, publish
`dist`). No env vars or secrets are needed — the data is public.

1. In Netlify, **Add new site → Import from Git**, pick
   `Disasters-Learning-Portal/disasters-aws-conversion`, branch **`main`**. `netlify.toml`
   supplies the build settings. Netlify auto-deploys on push to `main`.
2. **Seed the live source once:** run the *LOE Capacity Report* Action via **Run workflow**
   with `pi = "All PIs"` so the `loe-report/all-pis` branch exists. Until then the site
   serves the bundled snapshot automatically.

After that, each weekly report run updates the numbers on next page load — no redeploy.

## Keeping the recompute in sync

The aggregation in [`src/compute.ts`](src/compute.ts) mirrors
`.github/scripts/generate_loe_report.py`. Unedited rows reuse the generator's authoritative
per-row `weighted_fte` (computed from the full-precision PI fraction, which the CSV stores
only rounded), so the dashboard reconciles exactly with the report. If the generator's
columns or FTE math change, update `compute.ts` and re-check the `✓ matches baseline` badge.
