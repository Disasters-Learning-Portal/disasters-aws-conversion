import type { Headline } from "../compute";
import type { ReportContext } from "../types";

function Stat({ label, value, danger }: { label: string; value: string | number; danger?: boolean }) {
  return (
    <div className={`stat${danger ? " danger" : ""}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

export default function HeadlineCards({ headline, context }: { headline: Headline; context: ReportContext }) {
  return (
    <div className="cards">
      <Stat label="Objectives (with LOE)" value={headline.objectivesWithAllocations} />
      <Stat label="People allocated" value={headline.people} />
      <Stat label="Over-allocated (person·PI)" value={headline.overAllocatedPairs} danger={headline.overAllocatedPairs > 0} />
      <Stat label="Total raw FTE" value={headline.totalRawFte.toFixed(2)} />
      <Stat label="Total weighted FTE" value={headline.totalWeightedFte.toFixed(2)} />
      {context.missingLoe != null && <Stat label="Objectives missing LOE" value={context.missingLoe} />}
    </div>
  );
}
