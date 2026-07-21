// Data models mirroring the columns emitted by .github/scripts/generate_loe_report.py.

/** One row of loe_allocations.csv — the atomic unit and the what-if edit surface. */
export interface Allocation {
  /** Stable client id (does not come from CSV); used as React key + edit target. */
  id: string;
  pi: string;
  pi_window: string;
  issue_number: number;
  issue_title: string;
  issue_url: string;
  person: string;
  role: string;
  /** Editable in what-if mode. */
  fte: number;
  /** Original fte from the report; if fte still equals this, the row is unedited. */
  baseFte: number;
  obj_start: string;
  obj_end: string;
  /** Rounded (2-dp) fraction from the CSV — used only to recompute edited rows. */
  pi_fraction: number;
  /**
   * Authoritative per-row weighted FTE from the generator, computed with the FULL-precision
   * fraction. Used verbatim for unedited rows so aggregates reconcile exactly with the report;
   * edited rows fall back to fte * pi_fraction (see weightedOf in compute.ts).
   */
  weighted_fte: number;
}

/** One row of loe_by_person.csv (also the shape produced by computePersonAggs). */
export interface PersonAgg {
  pi: string;
  person: string;
  total_fte: number;
  weighted_fte: number;
  num_objectives: number;
  roles: string;
  over_allocated: boolean;
}

/** One row of loe_by_role.csv (also the shape produced by computeRoleAggs). */
export interface RoleAgg {
  pi: string;
  role: string;
  total_fte: number;
  weighted_fte: number;
  num_people: number;
  num_allocations: number;
}

/** Headline stats parsed from loe_summary.md (report context, not recomputed live). */
export interface ReportContext {
  generatedAt: string | null;
  openObjectives: number | null;
  missingLoe: number | null;
  partialWindow: number | null;
}

/** The full dataset loaded for the dashboard. */
export interface Dataset {
  source: "live" | "snapshot";
  allocations: Allocation[];
  /** Baseline aggregates straight from the CSVs, used to validate the recompute engine. */
  baselinePersons: PersonAgg[];
  baselineRoles: RoleAgg[];
  context: ReportContext;
}
