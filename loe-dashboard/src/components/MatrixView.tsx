import { useMemo, useState } from "react";
import { ROLE_ORDER, round2 } from "../compute";
import type { Allocation } from "../types";

interface Props {
  /** Already PI-filtered allocations (from App). */
  allocations: Allocation[];
  /** `${pi}||${person}` keys that are over-allocated in their PI. */
  overKeys: Set<string>;
  /** true when viewing "All PIs" (person totals then span PIs — surfaced in the hint). */
  showPi: boolean;
}

interface Objective {
  number: number;
  title: string;
  url: string;
  initiative: string;
}

interface Group {
  initiative: string;
  objectives: Objective[];
  total: number; // sum of raw FTE across the whole initiative
}

const ALL = "ALL";
const UNSPEC = "Unspecified";

/** 0 renders blank; otherwise 2-dp with trailing zeros trimmed (0.25, 0.8, 1.5). */
const fmt = (n: number): string => (n ? String(round2(n)) : "");

/** Initiatives sorted A→Z with "Unspecified" pinned last. */
function initiativeRank(a: string, b: string): number {
  if (a === UNSPEC) return 1;
  if (b === UNSPEC) return -1;
  return a.localeCompare(b);
}

/** Roles sorted by the canonical ROLE_ORDER, unknown roles last. */
function roleRank(r: string): number {
  const i = ROLE_ORDER.indexOf(r);
  return i === -1 ? ROLE_ORDER.length : i;
}

export default function MatrixView({ allocations, overKeys, showPi }: Props) {
  const [projectFilter, setProjectFilter] = useState(ALL);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const projects = useMemo(
    () => Array.from(new Set(allocations.map((a) => a.project))).sort(initiativeRank),
    [allocations],
  );

  const model = useMemo(() => {
    const rows =
      projectFilter === ALL ? allocations : allocations.filter((a) => a.project === projectFilter);
    const add = (m: Map<string, number>, k: string, v: number) => m.set(k, (m.get(k) || 0) + v);

    const objMap = new Map<number, Objective>();
    const cell = new Map<string, number>(); // person||role||issue -> fte
    const objTotal = new Map<number, number>(); // issue -> fte
    const roleTotal = new Map<string, number>(); // person||role -> fte  (Total per person per role)
    const personTotal = new Map<string, number>(); // person -> fte      (Total per person)
    const initPersonRole = new Map<string, number>(); // initiative||person||role -> fte
    const initTotal = new Map<string, number>(); // initiative -> fte
    const rolesByPerson = new Map<string, Set<string>>();
    const personPis = new Map<string, Set<string>>();
    let grand = 0;

    for (const a of rows) {
      const init = a.initiative || UNSPEC;
      if (!objMap.has(a.issue_number)) {
        objMap.set(a.issue_number, {
          number: a.issue_number,
          title: a.issue_title,
          url: a.issue_url,
          initiative: init,
        });
      }
      add(cell, `${a.person}||${a.role}||${a.issue_number}`, a.fte);
      objTotal.set(a.issue_number, (objTotal.get(a.issue_number) || 0) + a.fte);
      add(roleTotal, `${a.person}||${a.role}`, a.fte);
      add(personTotal, a.person, a.fte);
      add(initPersonRole, `${init}||${a.person}||${a.role}`, a.fte);
      add(initTotal, init, a.fte);
      grand += a.fte;
      if (!rolesByPerson.has(a.person)) rolesByPerson.set(a.person, new Set());
      rolesByPerson.get(a.person)!.add(a.role);
      if (!personPis.has(a.person)) personPis.set(a.person, new Set());
      personPis.get(a.person)!.add(a.pi);
    }

    const byInit = new Map<string, Objective[]>();
    for (const o of objMap.values()) {
      if (!byInit.has(o.initiative)) byInit.set(o.initiative, []);
      byInit.get(o.initiative)!.push(o);
    }
    const groups: Group[] = Array.from(byInit.entries())
      .map(([initiative, objs]) => ({
        initiative,
        objectives: objs.sort((x, y) => x.number - y.number),
        total: round2(initTotal.get(initiative) || 0),
      }))
      .sort((g1, g2) => initiativeRank(g1.initiative, g2.initiative));

    const people = Array.from(personTotal.keys()).sort();
    const rolesOf = (p: string) =>
      Array.from(rolesByPerson.get(p) || []).sort((x, y) => roleRank(x) - roleRank(y) || x.localeCompare(y));

    // A person is flagged if any of their (PI,person) pairs is over-allocated.
    const overPerson = new Set<string>();
    for (const p of people) {
      for (const pi of personPis.get(p) || []) {
        if (overKeys.has(`${pi}||${p}`)) overPerson.add(p);
      }
    }

    const rowCount = people.reduce((n, p) => n + (rolesByPerson.get(p)?.size || 0), 0);

    return {
      groups,
      people,
      rolesOf,
      cell,
      objTotal,
      roleTotal,
      personTotal,
      initPersonRole,
      overPerson,
      grand: round2(grand),
      objectiveCount: objMap.size,
      rowCount,
    };
  }, [allocations, projectFilter, overKeys]);

  const toggle = (initiative: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(initiative) ? next.delete(initiative) : next.add(initiative);
      return next;
    });
  const isOpen = (initiative: string) => !collapsed.has(initiative);
  const expandAll = () => setCollapsed(new Set());
  const collapseAll = () => setCollapsed(new Set(model.groups.map((g) => g.initiative)));

  const { groups, people } = model;

  return (
    <div className="panel">
      <h2>Capacity Matrix — people × objectives</h2>
      <p className="hint">
        Raw FTE per person on each objective, grouped by <strong>Initiative</strong>. A person with
        more than one role gets one row per role; <strong>Per role</strong> sums that role,{" "}
        <strong>Per person</strong> sums all their roles. Click an initiative to collapse it into a
        single subtotal column; objective titles link to their GitHub tickets.
        {showPi && " Viewing all PIs — a person's total spans every PI in view."}
      </p>

      <div className="filters">
        <label>
          Project&nbsp;
          <select value={projectFilter} onChange={(e) => setProjectFilter(e.target.value)}>
            <option value={ALL}>All projects</option>
            {projects.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <button onClick={expandAll}>Expand all</button>
        <button onClick={collapseAll}>Collapse all</button>
        <span className="sub">
          {people.length} people · {model.rowCount} role-rows · {model.objectiveCount} objectives ·{" "}
          {groups.length} initiatives
        </span>
      </div>

      {people.length === 0 ? (
        <div className="notice">No allocations for this selection.</div>
      ) : (
        <div className="tbl-wrap matrix-wrap">
          <table className="matrix">
            <thead>
              <tr className="group">
                <th className="rowhead corner" colSpan={2} rowSpan={2}>
                  Person · Role
                </th>
                {groups.map((g) => {
                  const open = isOpen(g.initiative);
                  return (
                    <th
                      key={g.initiative}
                      className="grouphead"
                      colSpan={open ? g.objectives.length : 1}
                    >
                      <button className="chev" onClick={() => toggle(g.initiative)} title={open ? "Collapse" : "Expand"}>
                        <span className="tri">{open ? "▾" : "▸"}</span>
                        <span className="gname">{g.initiative}</span>
                        <span className="gtot">{fmt(g.total)}</span>
                      </button>
                    </th>
                  );
                })}
                <th className="rowhead-right num roletot" rowSpan={2}>
                  Per role
                </th>
                <th className="rowhead-right num total" rowSpan={2}>
                  Per person
                </th>
              </tr>
              <tr className="cols">
                {groups.map((g) =>
                  isOpen(g.initiative) ? (
                    g.objectives.map((o, i) => (
                      <th
                        key={o.number}
                        className={`objhead num${i === 0 ? " grpstart" : ""}`}
                        title={o.title}
                      >
                        {o.url ? (
                          <a href={o.url} target="_blank" rel="noreferrer">
                            {o.title}
                          </a>
                        ) : (
                          o.title
                        )}
                      </th>
                    ))
                  ) : (
                    <th key={g.initiative} className="objhead num grpstart sumcol" title={`${g.initiative} subtotal`}>
                      Σ {g.initiative}
                    </th>
                  ),
                )}
              </tr>
            </thead>

            <tbody>
              {people.map((person) => {
                const roles = model.rolesOf(person);
                const over = model.overPerson.has(person);
                return roles.map((role, ri) => (
                  <tr key={`${person}||${role}`} className={over ? "over" : ""}>
                    {ri === 0 && (
                      <td className="rowhead pcell" rowSpan={roles.length}>
                        <span className="pname">{person}</span>
                      </td>
                    )}
                    <td className="rowhead rcell">{role}</td>
                    {groups.map((g) =>
                      isOpen(g.initiative) ? (
                        g.objectives.map((o, i) => {
                          const v = model.cell.get(`${person}||${role}||${o.number}`) || 0;
                          return (
                            <td key={o.number} className={`num${i === 0 ? " grpstart" : ""}${v ? "" : " empty"}`}>
                              {fmt(v)}
                            </td>
                          );
                        })
                      ) : (
                        (() => {
                          const v = model.initPersonRole.get(`${g.initiative}||${person}||${role}`) || 0;
                          return (
                            <td key={g.initiative} className={`num grpstart subtotal${v ? "" : " empty"}`}>
                              {fmt(v)}
                            </td>
                          );
                        })()
                      ),
                    )}
                    <td className="num roletot">{fmt(model.roleTotal.get(`${person}||${role}`) || 0)}</td>
                    {ri === 0 && (
                      <td className={`num total${over ? " overtot" : ""}`} rowSpan={roles.length}>
                        {fmt(model.personTotal.get(person) || 0)}
                      </td>
                    )}
                  </tr>
                ));
              })}
            </tbody>

            <tfoot>
              <tr className="obj-totals">
                <td className="rowhead" colSpan={2}>
                  Total per objective
                </td>
                {groups.map((g) =>
                  isOpen(g.initiative) ? (
                    g.objectives.map((o, i) => (
                      <td key={o.number} className={`num${i === 0 ? " grpstart" : ""}`}>
                        {fmt(model.objTotal.get(o.number) || 0)}
                      </td>
                    ))
                  ) : (
                    <td key={g.initiative} className="num grpstart subtotal">
                      {fmt(g.total)}
                    </td>
                  ),
                )}
                <td className="num roletot" />
                <td className="num total">{fmt(model.grand)}</td>
              </tr>
              <tr className="team-totals">
                <td className="rowhead" colSpan={2}>
                  Total per initiative
                </td>
                {groups.map((g) => (
                  <td
                    key={g.initiative}
                    className="num grpstart grptotal"
                    colSpan={isOpen(g.initiative) ? g.objectives.length : 1}
                    title={`${g.initiative} — total FTE`}
                  >
                    {fmt(g.total)}
                  </td>
                ))}
                <td className="num roletot" />
                <td className="num total">{fmt(model.grand)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
