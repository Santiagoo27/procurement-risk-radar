import type { TargetScore } from "../lib/data";
import { pct } from "../lib/format";

export type Band = "high" | "elevated" | "typical";

export function band(percentile: number): Band {
  if (percentile >= 90) return "high";
  if (percentile >= 60) return "elevated";
  return "typical";
}

const STYLE: Record<Band, string> = {
  high: "border-blue-900 bg-blue-900 text-white",
  elevated: "border-blue-300 bg-blue-50 text-blue-900",
  typical: "border-line bg-white text-ink",
};

export function RiskBadge({ label, score }: { label: string; score: TargetScore }) {
  const b = band(score.percentile);
  return (
    <div className={`rounded-md border px-2 py-1 ${STYLE[b]}`}>
      <div className="text-xs opacity-80">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{pct(score.probability)}</div>
      <div className="text-xs opacity-80">
        higher than {Math.round(score.percentile)}% of recent contracts
      </div>
    </div>
  );
}
