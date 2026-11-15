import type { Signal } from "../lib/data";

export function Signals({ signals }: { signals: Signal[] }) {
  if (signals.length === 0) {
    return <p className="text-xs text-muted">No single factor stands out.</p>;
  }
  return (
    <ul className="space-y-0.5 text-xs">
      {signals.map((s) => (
        <li key={s.feature} className={s.provided ? "text-ink" : "text-muted"}>
          <span aria-hidden className="mr-1">▲</span>
          {s.label}
        </li>
      ))}
    </ul>
  );
}
