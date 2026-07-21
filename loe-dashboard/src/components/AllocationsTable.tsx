import { useMemo, useState } from "react";
import { round2 } from "../compute";
import type { Allocation } from "../types";

interface Props {
  /** PI-filtered allocations (the rows in the current view). */
  allocations: Allocation[];
  /** `${pi}||${person}` keys that are over-allocated, for highlight / filter. */
  overKeys: Set<string>;
  showPi: boolean;
  onFte: (id: string, fte: number) => void;
}

export default function AllocationsTable({ allocations, overKeys, showPi, onFte }: Props) {
  const [search, setSearch] = useState("");
  const [person, setPerson] = useState("ALL");
  const [role, setRole] = useState("ALL");
  const [overOnly, setOverOnly] = useState(false);

  const persons = useMemo(() => Array.from(new Set(allocations.map((a) => a.person))).sort(), [allocations]);
  const roles = useMemo(() => Array.from(new Set(allocations.map((a) => a.role))).sort(), [allocations]);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allocations.filter((a) => {
      if (person !== "ALL" && a.person !== person) return false;
      if (role !== "ALL" && a.role !== role) return false;
      if (overOnly && !overKeys.has(`${a.pi}||${a.person}`)) return false;
      if (q && !`${a.issue_number} ${a.issue_title} ${a.person} ${a.role}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [allocations, search, person, role, overOnly, overKeys]);

  return (
    <div className="panel">
      <h2>Allocations — what-if editor</h2>
      <p className="hint">
        Edit any <strong>FTE</strong> to model a re-balance. Person, role and headline totals recompute instantly.
        Edits stay in your browser and are never written back to GitHub — use <em>Export</em> to save a scenario.
      </p>

      <div className="filters">
        <input type="text" placeholder="Search issue / person / role…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ minWidth: 220 }} />
        <label>
          Person
          <select value={person} onChange={(e) => setPerson(e.target.value)}>
            <option value="ALL">All</option>
            {persons.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <label>
          Role
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="ALL">All</option>
            {roles.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </label>
        <label>
          <input type="checkbox" checked={overOnly} onChange={(e) => setOverOnly(e.target.checked)} />
          Over-allocated people only
        </label>
        <span className="sub">{rows.length} of {allocations.length} rows</span>
      </div>

      <div className="tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>Issue</th>
              <th>Objective</th>
              {showPi && <th>PI</th>}
              <th>Person</th>
              <th>Role</th>
              <th className="num">FTE</th>
              <th className="num">× frac</th>
              <th className="num">= weighted</th>
              <th>Window</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => {
              const over = overKeys.has(`${a.pi}||${a.person}`);
              return (
                <tr key={a.id} className={over ? "over" : ""}>
                  <td>
                    <a href={a.issue_url} target="_blank" rel="noreferrer">#{a.issue_number}</a>
                  </td>
                  <td title={a.issue_title} style={{ maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {a.issue_title}
                  </td>
                  {showPi && <td>{a.pi}</td>}
                  <td>{a.person}</td>
                  <td>{a.role}</td>
                  <td className="num">
                    <input
                      type="number"
                      step="0.05"
                      min="0"
                      value={a.fte}
                      onChange={(e) => {
                        const v = parseFloat(e.target.value);
                        onFte(a.id, isNaN(v) ? 0 : Math.max(0, v));
                      }}
                    />
                  </td>
                  <td className="num">{a.pi_fraction.toFixed(2)}</td>
                  <td className="num">{round2(a.fte * a.pi_fraction).toFixed(2)}</td>
                  <td className="mono sub">{a.obj_start} → {a.obj_end}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
