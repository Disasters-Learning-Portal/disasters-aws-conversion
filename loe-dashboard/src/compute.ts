// What-if recompute engine. Mirrors the aggregation in
// .github/scripts/generate_loe_report.py so the browser reproduces the Python
// generator's numbers exactly from the atomic allocation rows.
import type { Allocation, PersonAgg, RoleAgg } from "./types";

/** Canonical role display order (matches ALLOWED_ROLES in the generator). */
export const ROLE_ORDER = [
  "PM",
  "Frontend",
  "Backend",
  "Geospatial",
  "Data Curator",
  "Comms",
  "ML",
  "Designer",
  "Jupyterhub",
];

/** Over-allocation threshold: raw FTE summed per (person, PI) above this is flagged. */
export const CAPACITY = 1.0;

/** Round half-up to 2 decimals, matching the generator's rounding of weighted FTE. */
export function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

/**
 * Per-allocation weighted FTE. For unedited rows, use the generator's authoritative
 * value verbatim (it was computed from the full-precision fraction, which the CSV only
 * stores rounded) so aggregates reconcile exactly with the report. For what-if-edited
 * rows, recompute from the rounded fraction — the best available estimate for a
 * hypothetical the generator never saw.
 */
export function weightedOf(a: Allocation): number {
  return a.fte === a.baseFte ? a.weighted_fte : round2(a.fte * a.pi_fraction);
}

/** Aggregate allocations to per-(person, PI) rows. */
export function computePersonAggs(allocs: Allocation[]): PersonAgg[] {
  const map = new Map<
    string,
    {
      pi: string;
      person: string;
      totalRaw: number;
      totalWeighted: number;
      issues: Set<number>;
      roles: Set<string>;
    }
  >();
  for (const a of allocs) {
    const key = `${a.pi}||${a.person}`;
    let g = map.get(key);
    if (!g) {
      g = { pi: a.pi, person: a.person, totalRaw: 0, totalWeighted: 0, issues: new Set(), roles: new Set() };
      map.set(key, g);
    }
    g.totalRaw += a.fte;
    g.totalWeighted += weightedOf(a);
    g.issues.add(a.issue_number);
    g.roles.add(a.role);
  }
  const out: PersonAgg[] = [];
  for (const g of map.values()) {
    const total_fte = round2(g.totalRaw);
    out.push({
      pi: g.pi,
      person: g.person,
      total_fte,
      weighted_fte: round2(g.totalWeighted),
      num_objectives: g.issues.size,
      roles: Array.from(g.roles).sort().join(";"),
      over_allocated: total_fte > CAPACITY,
    });
  }
  out.sort((a, b) => a.pi.localeCompare(b.pi) || b.total_fte - a.total_fte || a.person.localeCompare(b.person));
  return out;
}

/** Aggregate allocations to per-(role, PI) rows. */
export function computeRoleAggs(allocs: Allocation[]): RoleAgg[] {
  const map = new Map<
    string,
    { pi: string; role: string; totalRaw: number; totalWeighted: number; people: Set<string>; count: number }
  >();
  for (const a of allocs) {
    const key = `${a.pi}||${a.role}`;
    let g = map.get(key);
    if (!g) {
      g = { pi: a.pi, role: a.role, totalRaw: 0, totalWeighted: 0, people: new Set(), count: 0 };
      map.set(key, g);
    }
    g.totalRaw += a.fte;
    g.totalWeighted += weightedOf(a);
    g.people.add(a.person);
    g.count += 1;
  }
  const out: RoleAgg[] = [];
  for (const g of map.values()) {
    out.push({
      pi: g.pi,
      role: g.role,
      total_fte: round2(g.totalRaw),
      weighted_fte: round2(g.totalWeighted),
      num_people: g.people.size,
      num_allocations: g.count,
    });
  }
  const rank = (r: string) => {
    const i = ROLE_ORDER.indexOf(r);
    return i === -1 ? ROLE_ORDER.length : i;
  };
  out.sort((a, b) => a.pi.localeCompare(b.pi) || rank(a.role) - rank(b.role) || a.role.localeCompare(b.role));
  return out;
}

export interface Headline {
  objectivesWithAllocations: number;
  people: number;
  pis: number;
  overAllocatedPairs: number;
  totalRawFte: number;
  totalWeightedFte: number;
}

/** Live headline stats derived from the (possibly edited) allocations in view. */
export function computeHeadline(allocs: Allocation[], persons: PersonAgg[]): Headline {
  const issues = new Set<number>();
  const people = new Set<string>();
  const pis = new Set<string>();
  let raw = 0;
  let weighted = 0;
  for (const a of allocs) {
    issues.add(a.issue_number);
    people.add(a.person);
    pis.add(a.pi);
    raw += a.fte;
    weighted += weightedOf(a);
  }
  return {
    objectivesWithAllocations: issues.size,
    people: people.size,
    pis: pis.size,
    overAllocatedPairs: persons.filter((p) => p.over_allocated).length,
    totalRawFte: round2(raw),
    totalWeightedFte: round2(weighted),
  };
}

export interface BaselineCheck {
  ok: boolean;
  checked: number;
  mismatches: string[];
}

const EPS = 0.005; // sub-cent: only float noise tolerated, real cent-level drift fails

/** Validate that the client recompute equals the Python-generated baseline CSVs. */
export function validateBaseline(
  computedPersons: PersonAgg[],
  baselinePersons: PersonAgg[],
  computedRoles: RoleAgg[],
  baselineRoles: RoleAgg[],
): BaselineCheck {
  const mismatches: string[] = [];
  const pIndex = new Map(computedPersons.map((p) => [`${p.pi}||${p.person}`, p]));
  for (const b of baselinePersons) {
    const c = pIndex.get(`${b.pi}||${b.person}`);
    if (!c) {
      mismatches.push(`person missing: ${b.pi} / ${b.person}`);
      continue;
    }
    if (Math.abs(c.total_fte - b.total_fte) > EPS)
      mismatches.push(`${b.pi}/${b.person} total_fte ${c.total_fte} != ${b.total_fte}`);
    if (Math.abs(c.weighted_fte - b.weighted_fte) > EPS)
      mismatches.push(`${b.pi}/${b.person} weighted_fte ${c.weighted_fte} != ${b.weighted_fte}`);
    if (c.num_objectives !== b.num_objectives)
      mismatches.push(`${b.pi}/${b.person} num_objectives ${c.num_objectives} != ${b.num_objectives}`);
    if (c.over_allocated !== b.over_allocated)
      mismatches.push(`${b.pi}/${b.person} over_allocated ${c.over_allocated} != ${b.over_allocated}`);
  }
  const rIndex = new Map(computedRoles.map((r) => [`${r.pi}||${r.role}`, r]));
  for (const b of baselineRoles) {
    const c = rIndex.get(`${b.pi}||${b.role}`);
    if (!c) {
      mismatches.push(`role missing: ${b.pi} / ${b.role}`);
      continue;
    }
    if (Math.abs(c.total_fte - b.total_fte) > EPS)
      mismatches.push(`${b.pi}/${b.role} total_fte ${c.total_fte} != ${b.total_fte}`);
    if (c.num_people !== b.num_people)
      mismatches.push(`${b.pi}/${b.role} num_people ${c.num_people} != ${b.num_people}`);
    if (c.num_allocations !== b.num_allocations)
      mismatches.push(`${b.pi}/${b.role} num_allocations ${c.num_allocations} != ${b.num_allocations}`);
  }
  return { ok: mismatches.length === 0, checked: baselinePersons.length + baselineRoles.length, mismatches };
}
