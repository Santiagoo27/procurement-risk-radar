import type { Topology } from "topojson-specification";

export type Metrics = Record<string, number>;

export interface Summary {
  as_of: string;
  observed_period: [string, string];
  min_n: number;
  n_closed: number;
  n_open_scored: number;
  predicted_layer_available: boolean;
  min_open_for_predicted_layer: number;
  national: {
    value_addition_rate: number | null;
    extension_rate: number | null;
    predicted_value_addition: number | null;
    predicted_extension: number | null;
  };
  model_metrics: Record<string, Record<string, Metrics>>;
  bundle_version: string;
  model_features?: string[];
  model_features_by_target?: Record<string, string[]>;
  coverage: { department_share: number; municipality_share: number };
}

export interface RegionStats {
  code: string;
  name: string | null;
  dpto_code?: string | null;
  n_closed: number;
  value_addition_rate: number | null;
  extension_rate: number | null;
  n_open: number;
  predicted_value_addition: number | null;
  predicted_extension: number | null;
}

export interface Entity extends Omit<RegionStats, "code"> {
  buyer_id: string;
  dpto_code: string | null;
  mpio_code: string | null;
  dpto_slug: string;
}

export interface Signal {
  feature: string;
  label: string;
  provided: boolean;
  contribution: number;
}

export interface TargetScore {
  probability: number;
  percentile: number;
  top_signals: Signal[];
}

export interface OpenContract {
  /** Null for contracts with a natural-person supplier (identifier withheld). */
  id_contrato: string | null;
  url: string | null;
  supplier_is_natural_person?: boolean;
  signed_at: string | null;
  contract_type: string | null;
  procurement_method: string | null;
  award_value: number | null;
  planned_duration_days: number | null;
  value_addition: TargetScore;
  time_extension: TargetScore;
}

export type EntityShard = Record<string, { top_open: OpenContract[] }>;

export class DataError extends Error {}

const cache = new Map<string, Promise<unknown>>();

export function resetDataCache(): void {
  cache.clear();
}

function load<T>(path: string, label: string): Promise<T> {
  const cached = cache.get(path);
  if (cached) return cached as Promise<T>;
  const promise = fetch(path).then(async (response) => {
    if (!response.ok) {
      throw new DataError(`Could not load ${label} (HTTP ${response.status}).`);
    }
    return (await response.json()) as T;
  }).catch((error: unknown) => {
    cache.delete(path);
    throw error instanceof DataError
      ? error
      : new DataError(`Could not load ${label}: ${String(error)}`);
  });
  cache.set(path, promise);
  return promise;
}

export const loadSummary = () => load<Summary>("/data/summary.json", "summary");
export const loadDepartments = () => load<RegionStats[]>("/data/departments.json", "departments");
export const loadMunicipalities = () =>
  load<RegionStats[]>("/data/municipalities.json", "municipalities");
export const loadEntities = () => load<Entity[]>("/data/entities.json", "entities");
export const loadEntityShard = (slug: string) =>
  load<EntityShard>(`/data/entities/${slug}.json`, `entities of ${slug}`);
export const loadTopology = () =>
  load<Topology>("/geo/colombia-municipalities.topo.json", "map boundaries");

export interface Monitoring {
  as_of: string;
  status: "ok" | "watch" | "insufficient_data";
  n_current: number;
  windows: { reference: [string | null, string]; current: [string, string] };
  feature_drift: { feature: string; label: string; psi: number | null; shifted: boolean;
    expected?: boolean }[];
  score_shift: { reference_mean: number | null; current_mean: number | null };
  realized: { pr_auc: number | null; n: number; test_pr_auc: number | null;
    roc_auc?: number | null; test_roc_auc?: number | null;
    positive_rate?: number | null; reason: string | null };
}

/** Optional: null when the weekly job has not produced a report yet. */
export const loadMonitoring = () =>
  load<Monitoring>("/data/monitoring.json", "monitoring").catch(() => null);

export interface AmendmentSize {
  since: string | null;
  n_contracts_observed: number;
  n_increased: number;
  median_increase_pct: number | null;
  p75_increase_pct: number | null;
  p90_increase_pct: number | null;
  share_over_30pct: number | null;
  reason: string | null;
}

/** Optional: null until the weekly job has produced it. */
export const loadAmendmentSize = () =>
  load<AmendmentSize>("/data/amendment-size.json", "amendment size").catch(() => null);
