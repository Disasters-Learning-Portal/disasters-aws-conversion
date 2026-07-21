export type Tab = "matrix" | "dashboard";

interface Props {
  active: Tab;
  onChange: (t: Tab) => void;
}

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "matrix", label: "Capacity Matrix", icon: "▦" },
  { id: "dashboard", label: "What-if Dashboard", icon: "🛠" },
];

/** Fixed bottom-left segmented control that switches the top-level view. */
export default function TabSwitcher({ active, onChange }: Props) {
  return (
    <nav className="tab-switcher" aria-label="View">
      {TABS.map((t) => (
        <button
          key={t.id}
          className={`tab-btn${active === t.id ? " active" : ""}`}
          aria-pressed={active === t.id}
          onClick={() => onChange(t.id)}
        >
          <span className="tab-ico" aria-hidden>
            {t.icon}
          </span>
          {t.label}
        </button>
      ))}
    </nav>
  );
}
