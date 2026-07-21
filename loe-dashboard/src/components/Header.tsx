import type { BaselineCheck } from "../compute";

interface Props {
  pis: string[];
  piFilter: string;
  onPiChange: (v: string) => void;
  source: "live" | "snapshot";
  generatedAt: string | null;
  baseline: BaselineCheck | null;
  edited: boolean;
  onReset: () => void;
  onExport: (kind: "alloc" | "person" | "role") => void;
  /** Reset/Export/what-if controls are only meaningful on the editable dashboard tab. */
  showEditControls: boolean;
}

export default function Header({
  pis,
  piFilter,
  onPiChange,
  source,
  generatedAt,
  baseline,
  edited,
  onReset,
  onExport,
  showEditControls,
}: Props) {
  return (
    <header className="topbar">
      <div>
        <h1>LOE / FTE Capacity Dashboard</h1>
        <div className="sub">
          Raw FTE summed per person per PI; <strong>&gt; 1.0 = over-allocated</strong>. Weighted FTE adjusts for
          objectives that cover only part of the PI.
        </div>
      </div>
      <div className="spacer" />
      <div className="controls">
        <span className={`badge ${source}`} title={source === "live" ? "Fetched from the loe-report/all-pis branch" : "Using the snapshot bundled with the site"}>
          {source === "live" ? "● live" : "● snapshot"}
        </span>
        {generatedAt && <span className="badge" title="Report generation time">as of {generatedAt}</span>}
        {baseline && (
          <span
            className={`badge ${baseline.ok ? "ok" : "warn"}`}
            title={baseline.ok ? `Client recompute matches the report baseline (${baseline.checked} checks)` : baseline.mismatches.slice(0, 8).join("\n")}
          >
            {baseline.ok ? `✓ matches baseline` : `⚠ ${baseline.mismatches.length} mismatch`}
          </span>
        )}
      </div>
      <div className="controls" style={{ width: "100%", marginTop: 4 }}>
        <label className="sub" htmlFor="pi">
          Program Increment&nbsp;
        </label>
        <select id="pi" autoComplete="off" value={piFilter} onChange={(e) => onPiChange(e.target.value)}>
          <option value="ALL">All PIs</option>
          {pis.map((pi) => (
            <option key={pi} value={pi}>
              {pi}
            </option>
          ))}
        </select>
        <div className="spacer" />
        {showEditControls && (
          <>
            {edited && <span className="badge warn" title="Numbers reflect your unsaved what-if edits">what-if edits active</span>}
            <button onClick={onReset} disabled={!edited} title="Discard what-if edits and restore the report values">
              Reset
            </button>
            <button onClick={() => onExport("alloc")}>Export allocations</button>
            <button onClick={() => onExport("person")}>Export by person</button>
            <button onClick={() => onExport("role")}>Export by role</button>
          </>
        )}
      </div>
    </header>
  );
}
