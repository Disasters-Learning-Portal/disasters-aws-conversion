import { Bar, BarChart, CartesianGrid, Cell, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PersonAgg } from "../types";

export default function PersonView({ persons, showPi }: { persons: PersonAgg[]; showPi: boolean }) {
  const data = persons.map((p) => ({
    name: showPi ? `${p.person} · ${p.pi}` : p.person,
    raw: p.total_fte,
    weighted: p.weighted_fte,
    over: p.over_allocated,
  }));
  const height = Math.max(220, data.length * 30 + 60);

  return (
    <div className="panel">
      <h2>Capacity by person</h2>
      <p className="hint">
        Raw FTE (blue; <span style={{ color: "var(--red)" }}>red when over 1.0</span>) vs weighted FTE (light). The dashed
        line is the 1.0 full-time cap.
      </p>
      <div style={{ width: "100%", height, maxHeight: 520, overflowY: "auto" }}>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} layout="vertical" margin={{ left: 10, right: 24, top: 8, bottom: 8 }} barCategoryGap={6}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" domain={[0, "dataMax"]} tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v: number) => v.toFixed(2)} />
            <Legend />
            <ReferenceLine x={1} stroke="var(--red)" strokeDasharray="5 3" />
            <Bar dataKey="raw" name="Raw FTE">
              {data.map((d, i) => (
                <Cell key={i} fill={d.over ? "var(--red)" : "var(--blue)"} />
              ))}
            </Bar>
            <Bar dataKey="weighted" name="Weighted FTE" fill="var(--blue-soft)" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="tbl-wrap" style={{ marginTop: 12 }}>
        <table>
          <thead>
            <tr>
              <th>Person</th>
              {showPi && <th>PI</th>}
              <th className="num">Raw FTE</th>
              <th className="num">Weighted</th>
              <th className="num">Objectives</th>
              <th>Roles</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {persons.map((p) => (
              <tr key={`${p.pi}-${p.person}`} className={p.over_allocated ? "over" : ""}>
                <td>{p.person}</td>
                {showPi && <td>{p.pi}</td>}
                <td className="num">{p.total_fte.toFixed(2)}</td>
                <td className="num">{p.weighted_fte.toFixed(2)}</td>
                <td className="num">{p.num_objectives}</td>
                <td>{p.roles}</td>
                <td>
                  <span className={`tag ${p.over_allocated ? "over" : "ok"}`}>{p.over_allocated ? "over" : "ok"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
