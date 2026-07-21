// Client-side CSV export of the (possibly edited) what-if scenario.
// Column orders match the generator's output exactly so exports are drop-in comparable.
import type { Allocation, PersonAgg, RoleAgg } from "./types";

function cell(v: string | number | boolean): string {
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toCsv(headers: string[], rows: (string | number | boolean)[][]): string {
  return [headers.join(","), ...rows.map((r) => r.map(cell).join(","))].join("\n") + "\n";
}

export function allocationsToCsv(allocs: Allocation[]): string {
  return toCsv(
    ["pi", "pi_window", "issue_number", "issue_title", "issue_url", "project", "initiative", "team", "person", "role", "fte", "obj_start", "obj_end", "pi_fraction", "weighted_fte"],
    allocs.map((a) => [
      a.pi, a.pi_window, a.issue_number, a.issue_title, a.issue_url, a.project, a.initiative, a.team, a.person, a.role,
      a.fte, a.obj_start, a.obj_end, a.pi_fraction, Math.round((a.fte * a.pi_fraction + Number.EPSILON) * 100) / 100,
    ]),
  );
}

export function personsToCsv(persons: PersonAgg[]): string {
  return toCsv(
    ["pi", "person", "total_fte", "weighted_fte", "num_objectives", "roles", "over_allocated"],
    persons.map((p) => [p.pi, p.person, p.total_fte, p.weighted_fte, p.num_objectives, p.roles, p.over_allocated]),
  );
}

export function rolesToCsv(roles: RoleAgg[]): string {
  return toCsv(
    ["pi", "role", "total_fte", "weighted_fte", "num_people", "num_allocations"],
    roles.map((r) => [r.pi, r.role, r.total_fte, r.weighted_fte, r.num_people, r.num_allocations]),
  );
}

export function downloadCsv(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
