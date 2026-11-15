import { scaleQuantile } from "d3-scale";
import type { RegionStats } from "./data";

// Sequential blue ramp (validated reference palette, steps 150/300/450/550/700).
export const RAMP = ["#b7d3f6", "#6da7ec", "#2a78d6", "#1c5cab", "#0d366b"];
export const NO_DATA = "#e4e7eb";

type Field = "value_addition_rate" | "extension_rate" | "predicted_value_addition";

export interface Layer {
  id: string;
  label: string;
  short: string;
  field: Field;
  estimate: boolean;
  description: string;
}

export const LAYERS: Layer[] = [
  {
    id: "observed_value_addition",
    label: "Value additions (observed)",
    short: "Value additions",
    field: "value_addition_rate",
    estimate: false,
    description: "Share of closed contracts signed 2022–2024 that later received a value addition.",
  },
  {
    id: "observed_extension",
    label: "Time extensions (observed)",
    short: "Time extensions",
    field: "extension_rate",
    estimate: false,
    description: "Share of closed contracts signed 2022–2024 whose term was extended.",
  },
  {
    id: "predicted_value_addition",
    label: "Predicted value-addition risk, open contracts",
    short: "Predicted risk",
    field: "predicted_value_addition",
    estimate: true,
    description:
      "Average model probability that contracts still in execution will receive a value " +
      "addition. This is an estimate, not an observation.",
  },
];

export interface Bin {
  color: string;
  from: number;
  to: number;
}

export interface ColorScale {
  color: (v: number | null | undefined) => string;
  bins: Bin[];
}

export function colorScale(values: (number | null | undefined)[]): ColorScale {
  const present = values.filter((v): v is number => v !== null && v !== undefined && !isNaN(v));
  if (present.length === 0) return { color: () => NO_DATA, bins: [] };
  const q = scaleQuantile<string>().domain(present).range(RAMP);
  const thresholds = q.quantiles();
  const min = Math.min(...present);
  const max = Math.max(...present);
  const edges = [min, ...thresholds, max];
  const bins = RAMP.map((color, i) => ({ color, from: edges[i], to: edges[i + 1] }));
  return {
    color: (v) => (v === null || v === undefined || isNaN(v) ? NO_DATA : q(v)),
    bins,
  };
}

export function valueOf(stats: RegionStats | undefined, layer: Layer): number | null {
  if (!stats) return null;
  return stats[layer.field] ?? null;
}
