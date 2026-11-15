import { Link } from "react-router-dom";
import type { Entity, RegionStats } from "../lib/data";
import { count, pct } from "../lib/format";
import type { Layer } from "../lib/scale";

interface Props {
  region: RegionStats;
  level: "department" | "municipality";
  layer: Layer;
  minN: number;
  national: number | null;
  entities: Entity[];
}

const TOP = 10;

export function RegionPanel({ region, level, layer, minN, national, entities }: Props) {
  const value = region[layer.field];
  const n = layer.estimate ? region.n_open : region.n_closed;
  const ranked = entities
    .filter((e) => (layer.estimate ? e.n_open : e.n_closed) >= minN && e[layer.field] !== null)
    .sort((a, b) => (b[layer.field] ?? 0) - (a[layer.field] ?? 0))
    .slice(0, TOP);

  return (
    <section className="space-y-4" aria-live="polite">
      <div>
        <p className="text-xs uppercase tracking-wide text-muted">{level}</p>
        <h2 className="text-xl font-semibold">{region.name ?? region.code}</h2>
      </div>

      {value === null ? (
        <p className="rounded-md bg-paper p-3 text-sm text-muted">
          Fewer than {minN} {layer.estimate ? "open" : "closed"} contracts here, so no rate
          is shown ({count(n)} in the data).
        </p>
      ) : (
        <dl className="grid grid-cols-2 gap-3">
          <div className="rounded-md bg-paper p-3">
            <dt className="text-xs text-muted">{layer.short}</dt>
            <dd className="text-2xl font-semibold">{pct(value)}</dd>
            <dd className="text-xs text-muted">n = {count(n)}</dd>
          </div>
          <div className="rounded-md bg-paper p-3">
            <dt className="text-xs text-muted">Colombia</dt>
            <dd className="text-2xl font-semibold text-muted">{pct(national)}</dd>
          </div>
        </dl>
      )}

      <div>
        <h3 className="mb-2 text-sm font-medium">
          Buyers with the highest {layer.short.toLowerCase()}
        </h3>
        {ranked.length === 0 ? (
          <p className="text-sm text-muted">No buyer here has at least {minN} contracts.</p>
        ) : (
          <ol className="divide-y divide-line text-sm">
            {ranked.map((e) => (
              <li key={e.buyer_id} className="flex items-baseline justify-between gap-3 py-1.5">
                <Link className="truncate text-accent hover:underline"
                  to={`/entity/${e.buyer_id}`}>{e.name ?? e.buyer_id}</Link>
                <span className="shrink-0 text-right tabular-nums">
                  {pct(e[layer.field])}
                  <span className="block text-xs text-muted">
                    n = {count(layer.estimate ? e.n_open : e.n_closed)}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
