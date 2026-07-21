import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { RoleAgg } from "../types";

export default function RoleView({ roles, showPi }: { roles: RoleAgg[]; showPi: boolean }) {
  const data = roles.map((r) => ({
    name: showPi ? `${r.role} · ${r.pi}` : r.role,
    raw: r.total_fte,
    weighted: r.weighted_fte,
  }));
  const height = Math.max(220, data.length * 30 + 60);

  return (
    <div className="panel">
      <h2>Capacity by role</h2>
      <p className="hint">Total raw and weighted FTE demanded per role — useful for staffing / hiring signals.</p>
      <div style={{ width: "100%", height, maxHeight: 520, overflowY: "auto" }}>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} layout="vertical" margin={{ left: 10, right: 24, top: 8, bottom: 8 }} barCategoryGap={6}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" domain={[0, "dataMax"]} tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v: number) => v.toFixed(2)} />
            <Legend />
            <Bar dataKey="raw" name="Raw FTE" fill="var(--blue)" />
            <Bar dataKey="weighted" name="Weighted FTE" fill="var(--blue-soft)" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="tbl-wrap" style={{ marginTop: 12 }}>
        <table>
          <thead>
            <tr>
              <th>Role</th>
              {showPi && <th>PI</th>}
              <th className="num">Raw FTE</th>
              <th className="num">Weighted</th>
              <th className="num">People</th>
              <th className="num">Allocations</th>
            </tr>
          </thead>
          <tbody>
            {roles.map((r) => (
              <tr key={`${r.pi}-${r.role}`}>
                <td>{r.role}</td>
                {showPi && <td>{r.pi}</td>}
                <td className="num">{r.total_fte.toFixed(2)}</td>
                <td className="num">{r.weighted_fte.toFixed(2)}</td>
                <td className="num">{r.num_people}</td>
                <td className="num">{r.num_allocations}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
