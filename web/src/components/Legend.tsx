import { pct } from "../lib/format";
import { NO_DATA, type ColorScale } from "../lib/scale";

export function Legend({ title, scale }: { title: string; scale: ColorScale }) {
  return (
    <figure className="text-sm" aria-label={`Legend: ${title}`}>
      <figcaption className="mb-1 font-medium text-ink">{title}</figcaption>
      <ul className="flex flex-wrap gap-x-3 gap-y-1">
        {scale.bins.map((bin) => (
          <li key={bin.color} className="flex items-center gap-1.5 text-muted">
            <span className="inline-block h-3 w-5 rounded-sm" style={{ background: bin.color }}
              aria-hidden />
            <span>{pct(bin.from)} – {pct(bin.to)}</span>
          </li>
        ))}
        <li className="flex items-center gap-1.5 text-muted">
          <span className="inline-block h-3 w-5 rounded-sm border border-line"
            style={{ background: NO_DATA }} aria-hidden />
          <span>Not enough data</span>
        </li>
      </ul>
    </figure>
  );
}
