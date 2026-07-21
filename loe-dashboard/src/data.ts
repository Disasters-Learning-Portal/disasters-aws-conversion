// Loads the latest LOE report data.
//
// Primary source: the public `loe-report/all-pis` branch on GitHub (raw URLs), which
// always holds the newest "All PIs" report. If that branch/file is unavailable (e.g. it
// has not been seeded yet, or offline), fall back to the snapshot bundled in public/data/.
import Papa from "papaparse";
import type { Allocation, Dataset, PersonAgg, ReportContext, RoleAgg } from "./types";

const RAW_BASE =
  "https://raw.githubusercontent.com/Disasters-Learning-Portal/disasters-aws-conversion/loe-report/all-pis/reports";
const LOCAL_BASE = "data"; // resolved against the site root -> public/data/

const FILES = {
  allocations: "loe_allocations.csv",
  persons: "loe_by_person.csv",
  roles: "loe_by_role.csv",
  summary: "loe_summary.md",
} as const;

async function fetchText(base: string, file: string): Promise<string> {
  const url = `${base}/${file}?t=${Date.now()}`; // cache-buster: always newest report
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return res.text();
}

function parseRows(text: string): Record<string, string>[] {
  const res = Papa.parse<Record<string, string>>(text.trim(), { header: true, skipEmptyLines: true });
  return res.data;
}

function parseAllocations(text: string): Allocation[] {
  return parseRows(text).map((r, i) => ({
    id: `${r.issue_number}-${r.person}-${r.role}-${i}`,
    pi: r.pi ?? "",
    pi_window: r.pi_window ?? "",
    issue_number: parseInt(r.issue_number, 10),
    issue_title: r.issue_title ?? "",
    issue_url: r.issue_url ?? "",
    // Backward-compatible: CSVs written before these columns existed (or with the field
    // blank on the board) group under "Unspecified" rather than an empty label.
    project: r.project || "Unspecified",
    initiative: r.initiative || "Unspecified",
    team: r.team || "Unspecified",
    person: r.person ?? "",
    role: r.role ?? "",
    fte: parseFloat(r.fte) || 0,
    baseFte: parseFloat(r.fte) || 0,
    obj_start: r.obj_start ?? "",
    obj_end: r.obj_end ?? "",
    pi_fraction: parseFloat(r.pi_fraction) || 0,
    weighted_fte: parseFloat(r.weighted_fte) || 0,
  }));
}

function parsePersons(text: string): PersonAgg[] {
  return parseRows(text).map((r) => ({
    pi: r.pi ?? "",
    person: r.person ?? "",
    total_fte: parseFloat(r.total_fte) || 0,
    weighted_fte: parseFloat(r.weighted_fte) || 0,
    num_objectives: parseInt(r.num_objectives, 10) || 0,
    roles: r.roles ?? "",
    over_allocated: String(r.over_allocated).trim().toLowerCase() === "true",
  }));
}

function parseRoles(text: string): RoleAgg[] {
  return parseRows(text).map((r) => ({
    pi: r.pi ?? "",
    role: r.role ?? "",
    total_fte: parseFloat(r.total_fte) || 0,
    weighted_fte: parseFloat(r.weighted_fte) || 0,
    num_people: parseInt(r.num_people, 10) || 0,
    num_allocations: parseInt(r.num_allocations, 10) || 0,
  }));
}

function parseSummary(md: string): ReportContext {
  const num = (re: RegExp): number | null => {
    const m = md.match(re);
    return m ? parseInt(m[1], 10) : null;
  };
  const gen = md.match(/_Generated:\s*([^_]+)_/);
  return {
    generatedAt: gen ? gen[1].trim() : null,
    openObjectives: num(/Open Objective tickets:\*\*\s*(\d+)/),
    missingLoe: num(/Missing \/ empty LOE:\*\*\s*(\d+)/),
    partialWindow: num(/Partial-window objectives:\*\*\s*(\d+)/),
  };
}

export async function loadDataset(): Promise<Dataset> {
  let source: Dataset["source"];
  let base: string;
  let allocText: string;

  // Probe the live source once; reuse its body if it succeeds.
  try {
    allocText = await fetchText(RAW_BASE, FILES.allocations);
    base = RAW_BASE;
    source = "live";
  } catch {
    base = LOCAL_BASE;
    source = "snapshot";
    allocText = await fetchText(LOCAL_BASE, FILES.allocations);
  }

  const [personText, roleText, summaryText] = await Promise.all([
    fetchText(base, FILES.persons),
    fetchText(base, FILES.roles),
    fetchText(base, FILES.summary).catch(() => ""),
  ]);

  return {
    source,
    allocations: parseAllocations(allocText),
    baselinePersons: parsePersons(personText),
    baselineRoles: parseRoles(roleText),
    context: parseSummary(summaryText),
  };
}
